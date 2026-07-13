from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib

import pytest

from structural_analysis.io.midas.v2.lexer import lex_mgt_bytes
from structural_analysis.io.midas.v2.ranges import RangeSyntaxError, expand_id_expression
from structural_analysis.io.midas.v2.tokens import NewlineStyle


def test_lexer_preserves_bom_crlf_headers_comments_and_occurrences() -> None:
    source = (
        b"\xef\xbb\xbf; preamble\r\n"
        b"*VERSION ; product version\r\n"
        b"2024\r\n"
        b"*VENDOR-EXT, alpha, beta ; unknown block\r\n"
        b"1, 2 ; row comment\r\n"
        b"*VENDOR-EXT, gamma\r\n"
        b"3\r\n"
        b"*ENDDATA\r\n"
    )

    document = lex_mgt_bytes(source, source_name="bom-crlf.mgt")

    assert document.raw_bytes == source
    assert document.source.sha256 == hashlib.sha256(source).hexdigest()
    assert document.source.byte_count == len(source)
    assert document.source.physical_line_count == 8
    assert document.source.newline_style is NewlineStyle.CRLF
    assert document.source.has_utf8_bom is True
    assert b"".join(line.raw for line in document.physical_lines) == source

    root, version, first_unknown, second_unknown, enddata = document.blocks
    assert root.name == "ROOT"
    assert root.header is None
    assert root.occurrence_index == 0
    assert root.rows == ()
    assert root.physical_lines[0].text == "; preamble"
    assert version.name == "VERSION"
    assert version.header is not None
    assert version.header.comment == "product version"
    assert version.rows[0].text == "2024"
    assert first_unknown.name == "VENDOR-EXT"
    assert first_unknown.args == ("alpha", "beta")
    assert first_unknown.occurrence_index == 1
    assert first_unknown.rows[0].comments == ("row comment",)
    assert second_unknown.occurrence_index == 2
    assert second_unknown.args == ("gamma",)
    assert enddata.name == "ENDDATA"
    assert document.diagnostics == ()

    with pytest.raises(FrozenInstanceError):
        document.source.byte_count = 0  # type: ignore[misc]


def test_continuation_merges_rows_and_preserves_source_fragments() -> None:
    source = (
        b"*GROUP\n"
        b"G1, 1to3, \\ ; first\n"
        b"10to12by2, \\ \n"
        b"; between fragments\n"
        b"20 21 ; done\n"
        b"*ENDDATA\n"
    )

    document = lex_mgt_bytes(source)
    group = document.blocks[0]
    row = group.rows[0]

    assert row.text == "G1, 1to3, 10to12by2, 20 21"
    assert row.comments == ("first", "between fragments", "done")
    assert row.continued is True
    assert row.span.line_start == 2
    assert row.span.line_end == 5
    assert [fragment.number for fragment in row.raw_fragments] == [2, 3, 4, 5]
    raw_fragment = b"".join(fragment.raw for fragment in row.raw_fragments)
    assert row.raw_fragment_sha256 == hashlib.sha256(raw_fragment).hexdigest()
    assert group.span.line_start == 1
    assert group.span.line_end == 5


@pytest.mark.parametrize(
    ("source", "expected_blocks"),
    [
        (b"*GROUP\nA, 1, \\\n*NODE\n1, 0, 0, 0\n", ("GROUP", "NODE")),
        (b"*GROUP\nA, 1, \\", ("GROUP",)),
    ],
)
def test_unterminated_continuation_is_diagnosed_and_recovered(
    source: bytes,
    expected_blocks: tuple[str, ...],
) -> None:
    document = lex_mgt_bytes(source)

    assert tuple(block.name for block in document.blocks) == expected_blocks
    assert [diagnostic.code for diagnostic in document.diagnostics] == [
        "MGT_UNTERMINATED_CONTINUATION"
    ]
    assert document.blocks[0].rows[0].text == "A, 1,"
    assert document.blocks[0].rows[0].continued is True
    assert document.raw_bytes == source


def test_noncomment_content_after_enddata_is_preserved_and_diagnosed() -> None:
    source = b"*ENDDATA\r\n; allowed\n*NODE\r1, 0, 0, 0"

    document = lex_mgt_bytes(source)

    assert document.source.newline_style is NewlineStyle.MIXED
    assert document.source.physical_line_count == 4
    assert tuple(block.name for block in document.blocks) == ("ENDDATA",)
    assert [diagnostic.code for diagnostic in document.diagnostics] == [
        "MGT_CONTENT_AFTER_ENDDATA",
        "MGT_CONTENT_AFTER_ENDDATA",
    ]
    assert document.blocks[0].span.line_end == 4
    assert b"".join(line.raw for line in document.blocks[0].physical_lines) == source


def test_expand_id_expression_supports_lists_ranges_steps_and_descending_order() -> None:
    assert expand_id_expression("1 3, 5to9by2 12to10") == (
        1,
        3,
        5,
        7,
        9,
        12,
        11,
        10,
    )
    assert expand_id_expression("1 to 4 by 2") == (1, 3)
    assert expand_id_expression("4TO1BY3") == (4, 1)


@pytest.mark.parametrize("expression", ["1to5by0", "1 foo", "1to"])
def test_expand_id_expression_rejects_ambiguous_or_invalid_input(expression: str) -> None:
    with pytest.raises(RangeSyntaxError):
        expand_id_expression(expression)


def test_expand_id_expression_enforces_expansion_limit() -> None:
    with pytest.raises(RangeSyntaxError, match="max_items"):
        expand_id_expression("1to100", max_items=10)
