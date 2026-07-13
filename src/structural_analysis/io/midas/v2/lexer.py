"""Lossless, fail-closed lexer for MIDAS MGT v2 imports."""

from __future__ import annotations

from collections import Counter
import csv
import hashlib
from pathlib import Path
import re

from structural_analysis.io.midas.v2.tokens import (
    DiagnosticSeverity,
    HeaderToken,
    LexerDiagnostic,
    LogicalRow,
    MgtBlock,
    MgtDocument,
    NewlineStyle,
    PhysicalLine,
    SourceInfo,
    SourceSpan,
)


UTF8_BOM = b"\xef\xbb\xbf"
_PHYSICAL_LINE_RE = re.compile(rb"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+$")


class _BlockBuilder:
    __slots__ = ("args", "header", "name", "occurrence_index", "physical_lines", "rows")

    def __init__(
        self,
        *,
        name: str,
        args: tuple[str, ...],
        occurrence_index: int,
        header: HeaderToken | None,
        physical_lines: list[PhysicalLine] | None = None,
    ) -> None:
        self.name = name
        self.args = args
        self.occurrence_index = occurrence_index
        self.header = header
        self.rows: list[LogicalRow] = []
        self.physical_lines = physical_lines or []


class _PendingRow:
    __slots__ = ("comments", "physical_lines", "pieces", "used_continuation")

    def __init__(self) -> None:
        self.pieces: list[str] = []
        self.comments: list[str] = []
        self.physical_lines: list[PhysicalLine] = []
        self.used_continuation = False


def lex_mgt(path: str | Path) -> MgtDocument:
    """Read and lex an MGT file without altering its original byte stream."""

    source_path = Path(path)
    return lex_mgt_bytes(source_path.read_bytes(), source_name=str(source_path))


def lex_mgt_bytes(data: bytes, *, source_name: str = "<memory>") -> MgtDocument:
    """Lex UTF-8 MGT bytes into immutable, source-mapped blocks and rows."""

    raw_bytes = bytes(data)
    physical_lines = _decode_physical_lines(raw_bytes)
    source = SourceInfo(
        source_name=source_name,
        encoding="utf-8-sig" if raw_bytes.startswith(UTF8_BOM) else "utf-8",
        has_utf8_bom=raw_bytes.startswith(UTF8_BOM),
        sha256=_sha256(raw_bytes),
        byte_count=len(raw_bytes),
        physical_line_count=len(physical_lines),
        newline_style=_detect_newline_style(physical_lines),
    )

    occurrences: Counter[str] = Counter()
    completed_blocks: list[MgtBlock] = []
    diagnostics: list[LexerDiagnostic] = []
    current: _BlockBuilder | None = None
    pending: _PendingRow | None = None
    logical_index = 0
    ended = False

    def ensure_root() -> _BlockBuilder:
        nonlocal current
        if current is None:
            current = _BlockBuilder(
                name="ROOT",
                args=(),
                occurrence_index=0,
                header=None,
            )
        return current

    def finish_pending(*, unterminated: bool = False) -> None:
        nonlocal logical_index, pending
        if pending is None:
            return
        block = ensure_root()
        if unterminated:
            diagnostics.append(
                LexerDiagnostic(
                    code="MGT_UNTERMINATED_CONTINUATION",
                    message=(
                        "A continued logical row reached a new header or end of file "
                        "before a terminating data line."
                    ),
                    severity=DiagnosticSeverity.ERROR,
                    span=_span_for_lines(pending.physical_lines),
                    section=block.name,
                    block_occurrence=block.occurrence_index,
                )
            )
        logical_index += 1
        fragments = tuple(pending.physical_lines)
        block.rows.append(
            LogicalRow(
                section=block.name,
                block_occurrence=block.occurrence_index,
                block_row_index=len(block.rows),
                logical_index=logical_index,
                text=" ".join(piece for piece in pending.pieces if piece),
                comments=tuple(pending.comments),
                span=_span_for_lines(fragments),
                raw_fragments=fragments,
                raw_fragment_sha256=_sha256(b"".join(line.raw for line in fragments)),
                continued=pending.used_continuation,
            )
        )
        pending = None

    def finish_block() -> None:
        nonlocal current
        if current is None or not current.physical_lines:
            current = None
            return
        fragments = tuple(current.physical_lines)
        completed_blocks.append(
            MgtBlock(
                name=current.name,
                args=current.args,
                occurrence_index=current.occurrence_index,
                header=current.header,
                rows=tuple(current.rows),
                span=_span_for_lines(fragments),
                physical_lines=fragments,
            )
        )
        current = None

    for line in physical_lines:
        code, comment = _split_semicolon_comment(line.text)
        stripped = code.strip()

        if ended:
            assert current is not None
            current.physical_lines.append(line)
            if stripped:
                diagnostics.append(
                    LexerDiagnostic(
                        code="MGT_CONTENT_AFTER_ENDDATA",
                        message="Non-comment content appears after *ENDDATA.",
                        severity=DiagnosticSeverity.ERROR,
                        span=line.span,
                        section="ENDDATA",
                        block_occurrence=current.occurrence_index,
                    )
                )
            continue

        if stripped.startswith("*"):
            if pending is not None:
                finish_pending(unterminated=True)
            finish_block()
            header = _parse_header(line, stripped, comment)
            occurrences[header.name] += 1
            current = _BlockBuilder(
                name=header.name,
                args=header.args,
                occurrence_index=occurrences[header.name],
                header=header,
                physical_lines=[line],
            )
            if not header.name:
                diagnostics.append(
                    LexerDiagnostic(
                        code="MGT_EMPTY_HEADER",
                        message="An MGT header has no section name.",
                        severity=DiagnosticSeverity.ERROR,
                        span=line.span,
                        section="",
                        block_occurrence=current.occurrence_index,
                    )
                )
            if header.name == "ENDDATA":
                ended = True
            continue

        block = ensure_root()
        block.physical_lines.append(line)
        if not stripped:
            if pending is not None:
                pending.physical_lines.append(line)
                if comment is not None:
                    pending.comments.append(comment)
            continue

        piece, continues = _take_continuation(code)
        if pending is None:
            pending = _PendingRow()
        pending.pieces.append(piece)
        pending.physical_lines.append(line)
        if comment is not None:
            pending.comments.append(comment)
        pending.used_continuation = pending.used_continuation or continues
        if not continues:
            finish_pending()

    if pending is not None:
        finish_pending(unterminated=pending.used_continuation)
    finish_block()
    return MgtDocument(
        source=source,
        raw_bytes=raw_bytes,
        physical_lines=physical_lines,
        blocks=tuple(completed_blocks),
        diagnostics=tuple(diagnostics),
    )


def _decode_physical_lines(data: bytes) -> tuple[PhysicalLine, ...]:
    lines: list[PhysicalLine] = []
    byte_start = 0
    for number, match in enumerate(_PHYSICAL_LINE_RE.finditer(data), start=1):
        raw = match.group(0)
        content_bytes, newline = _remove_newline(raw)
        if number == 1 and content_bytes.startswith(UTF8_BOM):
            content_bytes = content_bytes[len(UTF8_BOM) :]
        text = content_bytes.decode("utf-8", errors="strict")
        byte_end = byte_start + len(raw)
        span = SourceSpan(
            line_start=number,
            line_end=number,
            byte_start=byte_start,
            byte_end=byte_end,
        )
        lines.append(
            PhysicalLine(
                number=number,
                span=span,
                raw=raw,
                text=text,
                newline=newline,
                raw_sha256=_sha256(raw),
            )
        )
        byte_start = byte_end
    return tuple(lines)


def _remove_newline(raw: bytes) -> tuple[bytes, str]:
    if raw.endswith(b"\r\n"):
        return raw[:-2], "\r\n"
    if raw.endswith(b"\n"):
        return raw[:-1], "\n"
    if raw.endswith(b"\r"):
        return raw[:-1], "\r"
    return raw, ""


def _detect_newline_style(lines: tuple[PhysicalLine, ...]) -> NewlineStyle:
    styles = {line.newline for line in lines if line.newline}
    if not styles:
        return NewlineStyle.NONE
    if len(styles) > 1:
        return NewlineStyle.MIXED
    style = next(iter(styles))
    return {
        "\n": NewlineStyle.LF,
        "\r\n": NewlineStyle.CRLF,
        "\r": NewlineStyle.CR,
    }[style]


def _split_semicolon_comment(text: str) -> tuple[str, str | None]:
    quote: str | None = None
    index = 0
    while index < len(text):
        char = text[index]
        if quote is not None:
            if char == quote:
                if index + 1 < len(text) and text[index + 1] == quote:
                    index += 2
                    continue
                quote = None
        elif char in {'"', "'"}:
            quote = char
        elif char == ";":
            return text[:index], text[index + 1 :].strip()
        index += 1
    return text, None


def _parse_header(
    line: PhysicalLine,
    stripped_code: str,
    comment: str | None,
) -> HeaderToken:
    body = stripped_code[1:].strip()
    fields = next(csv.reader([body], skipinitialspace=True), [])
    name = fields[0].strip().upper() if fields else ""
    args = tuple(field.strip() for field in fields[1:])
    return HeaderToken(
        name=name,
        args=args,
        comment=comment,
        span=line.span,
        raw_fragment=line,
        raw_fragment_sha256=line.raw_sha256,
    )


def _take_continuation(code: str) -> tuple[str, bool]:
    right_trimmed = code.rstrip()
    if right_trimmed.endswith("\\"):
        return right_trimmed[:-1].strip(), True
    return right_trimmed.strip(), False


def _span_for_lines(lines: tuple[PhysicalLine, ...] | list[PhysicalLine]) -> SourceSpan:
    if not lines:
        raise ValueError("a source span requires at least one physical line")
    return SourceSpan(
        line_start=lines[0].number,
        line_end=lines[-1].number,
        byte_start=lines[0].span.byte_start,
        byte_end=lines[-1].span.byte_end,
    )


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
