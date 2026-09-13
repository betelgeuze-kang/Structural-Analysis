"""Read explicitly selected rectangular measured XLSX tables without resampling.

Headers retain their original text. No unit, sampling interval, command history,
sensor correspondence or solver/training admission is inferred from a workbook.
"""

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import io
from pathlib import PurePosixPath
import re
import xml.etree.ElementTree as ET
import zipfile

from .measured_drift_load import _number


_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PACKAGE_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_MAX_BYTES = 16 * 1024 * 1024
_MAX_EXPANDED_BYTES = 128 * 1024 * 1024
_MAX_ROWS = 100_000


@dataclass(frozen=True)
class MeasuredNumericWorkbook:
    source_sha256: str
    sheet_name: str
    column_ids: tuple[str, ...]
    header_cells: tuple[tuple[str | None, ...], ...]
    source_row_numbers: tuple[int, ...]
    source_numeric_tokens: tuple[tuple[str, ...], ...]

    @property
    def point_count(self) -> int:
        return len(self.source_row_numbers)

    def channel(self, column_id: str) -> tuple[Decimal, ...]:
        index = self.column_ids.index(column_id)
        return tuple(Decimal(row[index]) for row in self.source_numeric_tokens)


def _column_number(name: str) -> int:
    if type(name) is not str or not re.fullmatch("[A-Z]{1,3}", name):
        raise ValueError("canonical spreadsheet column required")
    number = 0
    for char in name:
        number = 26 * number + ord(char) - ord("A") + 1
    return number


def _xml_bytes(archive: zipfile.ZipFile, name: str) -> bytes:
    raw = archive.read(name)
    # Only UTF-8 XML is supported. In particular, a UTF-16 declaration must not
    # evade the DTD/entity rejection below through embedded zero bytes.
    text = raw.decode("utf-8-sig")
    if "\x00" in text or "<!DOCTYPE" in text or "<!ENTITY" in text:
        raise ValueError("DTD and entity declarations are not measurement data")
    return raw


def _decode(
    archive: zipfile.ZipFile,
    sheet_name: str,
    columns: tuple[str, ...],
    header_rows: int,
) -> tuple[
    tuple[tuple[str | None, ...], ...], tuple[int, ...], tuple[tuple[str, ...], ...]
]:
    infos = archive.infolist()
    names = {item.filename for item in infos}
    if (
        len(infos) > 5000
        or len(names) != len(infos)
        or sum(item.file_size for item in infos) > _MAX_EXPANDED_BYTES
        or any(item.flag_bits & 1 for item in infos)
    ):
        raise ValueError("bounded unencrypted workbook with unique members required")
    strings = []
    if "xl/sharedStrings.xml" in names:
        shared = ET.fromstring(_xml_bytes(archive, "xl/sharedStrings.xml"))
        for item in shared.findall(_NS + "si"):
            strings.append("".join(node.text or "" for node in item.iter(_NS + "t")))
    workbook = ET.fromstring(_xml_bytes(archive, "xl/workbook.xml"))
    sheets = workbook.findall(_NS + "sheets/" + _NS + "sheet")
    selected = [sheet for sheet in sheets if sheet.get("name") == sheet_name]
    if len(selected) != 1:
        raise ValueError("one explicitly named source sheet required")
    rels = ET.fromstring(_xml_bytes(archive, "xl/_rels/workbook.xml.rels"))
    matching = [
        rel
        for rel in rels.findall(_PACKAGE_REL + "Relationship")
        if rel.get("Id") == selected[0].get(_REL + "id")
    ]
    if len(matching) != 1:
        raise ValueError("one worksheet relationship required")
    rel = matching[0]
    if (
        rel.get("TargetMode", "Internal") != "Internal"
        or rel.get("Type") != _REL[1:-1] + "/worksheet"
    ):
        raise ValueError("internal worksheet relationship required")
    target = rel.get("Target", "")
    member = target[1:] if target.startswith("/") else "xl/" + target
    if not target or ".." in PurePosixPath(member).parts or "\\" in member:
        raise ValueError("canonical internal worksheet target required")
    headers: list[tuple[str | None, ...]] = []
    row_numbers: list[int] = []
    observations: list[tuple[str, ...]] = []
    previous = 0
    stream = io.BytesIO(_xml_bytes(archive, member))
    for _, row in ET.iterparse(stream, events=("end",)):
        if row.tag != _NS + "row":
            continue
        index = int(row.attrib["r"])
        if index != previous + 1 or index > _MAX_ROWS + header_rows:
            raise ValueError("bounded consecutive source rows required")
        previous = index
        cells: dict[str, str | None] = {}
        for cell in row.findall(_NS + "c"):
            address = cell.get("r", "")
            match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]*)", address)
            if match is None or int(match[2]) != index:
                raise ValueError("cell address must match its source row")
            column = match[1]
            if column not in columns or column in cells:
                raise ValueError("unique cells within all declared columns required")
            if cell.find(_NS + "f") is not None:
                raise ValueError("formula cells are not original numeric observations")
            kind = cell.get("t", "n")
            value_nodes = cell.findall(_NS + "v")
            if len(value_nodes) > 1:
                raise ValueError("one original value per cell required")
            value = None if not value_nodes else value_nodes[0]
            token = None if value is None else value.text
            if index <= header_rows:
                if kind == "s" and token is not None:
                    if not re.fullmatch(r"[0-9]+", token) or int(token) >= len(strings):
                        raise ValueError("valid shared header string required")
                    cells[column] = strings[int(token)]
                elif kind == "inlineStr":
                    if value_nodes or len(cell.findall(_NS + "is")) != 1:
                        raise ValueError("one inline header value required")
                    cells[column] = "".join(
                        node.text or "" for node in cell.iter(_NS + "t")
                    )
                elif kind == "n" and token is None:
                    cells[column] = None
                else:
                    raise ValueError("text or blank source header required")
            else:
                if kind != "n" or token is None or cell.find(_NS + "is") is not None:
                    raise ValueError("every measured cell must be an original number")
                _number(token)
                cells[column] = token
        if index <= header_rows:
            headers.append(tuple(cells.get(column) for column in columns))
        else:
            if set(cells) != set(columns):
                raise ValueError("missing measurement cells cannot be interpolated")
            values = tuple(cells[column] for column in columns)
            if any(value is None for value in values):
                raise ValueError("numeric measurement cells required")
            observations.append(tuple(str(value) for value in values))
            row_numbers.append(index)
        row.clear()
    if len(headers) != header_rows or not observations:
        raise ValueError("complete headers and at least one observation required")
    return tuple(headers), tuple(row_numbers), tuple(observations)


def decode_measured_numeric_workbook(
    raw: bytes, *, sheet_name: str, columns: tuple[str, ...], header_rows: int
) -> MeasuredNumericWorkbook:
    """Read a complete declared table; reject missing, formula or extra cells.

    The caller names the sheet, all columns (A through its final column), and
    header extent. Repeated measurements, signed zero and decimal exponents
    remain in source order. Workbook dimensions do not replace actual cell checks.
    No workbook code, macros or formulas are executed; no files are extracted.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= _MAX_BYTES:
        raise ValueError("bounded nonempty XLSX bytes required")
    if type(sheet_name) is not str or not sheet_name:
        raise ValueError("explicit sheet name required")
    if type(header_rows) is not int or not 1 <= header_rows <= 32:
        raise ValueError("bounded explicit header row count required")
    if (
        type(columns) is not tuple
        or not 1 <= len(columns) <= 256
        or [_column_number(c) for c in columns] != list(range(1, len(columns) + 1))
    ):
        raise ValueError("all consecutive columns beginning at A required")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            headers, rows, tokens = _decode(archive, sheet_name, columns, header_rows)
    except (zipfile.BadZipFile, KeyError, ET.ParseError, UnicodeError) as exc:
        raise ValueError("well-formed measured XLSX table required") from exc
    return MeasuredNumericWorkbook(
        hashlib.sha256(raw).hexdigest(), sheet_name, columns, headers, rows, tokens
    )
