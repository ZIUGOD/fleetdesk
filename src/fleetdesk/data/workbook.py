"""Parse a single company workbook into domain records."""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterator
from datetime import date, datetime
from typing import Any

import openpyxl
from openpyxl.workbook.workbook import Workbook

from fleetdesk.data import schema
from fleetdesk.data.models import FileStatus, SourceRef, WorkbookData
from fleetdesk.data.schema import Kind, SheetSpec

#: Stop reading a tab after this many consecutive blank rows. The workbook ships with
#: formulas dragged down thousands of rows, and reading them all is slow.
EMPTY_ROW_LIMIT = 200
HEADER_SEARCH_ROWS = 30
MAX_COLUMNS = 40

Row = tuple[Any, ...]


class SchemaError(ValueError):
    """The workbook has the expected tab but not the expected columns."""


def read_workbook(path: str) -> WorkbookData:
    modified_at = datetime.fromtimestamp(os.path.getmtime(path))
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        if schema.IDENTIFYING_TAB not in workbook.sheetnames:
            return WorkbookData(
                path=path,
                status=FileStatus.IGNORED,
                reason=f"Formato não reconhecido (sem a aba {schema.IDENTIFYING_TAB})",
                modified_at=modified_at,
            )
        name = os.path.basename(path)
        data = WorkbookData(
            path=path,
            status=FileStatus.OK,
            modified_at=modified_at,
            freights=read_sheet(workbook, schema.FREIGHTS, name),
            fuel=read_sheet(workbook, schema.FUEL, name),
            tolls=read_sheet(workbook, schema.TOLLS, name),
            adjustments=read_sheet(workbook, schema.ADJUSTMENTS, name),
            payroll=read_sheet(workbook, schema.PAYROLL, name),
            vehicles=read_sheet(workbook, schema.VEHICLES, name),
        )
    finally:
        # Closing releases the file handle so Excel / Google Drive can save over it.
        workbook.close()

    # The payroll and per-vehicle tabs have no period column: they inherit the period
    # that most freights of the same workbook belong to.
    periods = Counter(f.period for f in data.freights if f.period)
    main_period = periods.most_common(1)[0][0] if periods else ""
    for summary in data.payroll:
        summary.period = main_period
    for vehicle in data.vehicles:
        vehicle.period = main_period
    return data


def read_sheet(workbook: Workbook, spec: SheetSpec, file_name: str = "") -> list[Any]:
    """Parse one tab. A missing tab yields no records; a malformed one raises SchemaError."""
    if spec.tab not in workbook.sheetnames:
        return []
    rows: Iterator[tuple[int, Row]] = enumerate(
        workbook[spec.tab].iter_rows(values_only=True, max_col=MAX_COLUMNS), start=1
    )
    positions = _locate_columns(rows, spec)
    anchor = positions[spec.columns[0].field]

    records: list[Any] = []
    blank_streak = 0
    for row_number, row in rows:
        first = row[anchor] if anchor < len(row) else None
        if first is None or first == "":
            blank_streak += 1
            if blank_streak >= EMPTY_ROW_LIMIT:
                break
            continue
        blank_streak = 0
        if spec.date_rows_only and not isinstance(first, date):
            continue
        if spec.skip_first_cell and _text(first).upper() in spec.skip_first_cell:
            continue
        values = {
            column.field: _convert(row[positions[column.field]], column.kind)
            if column.field in positions and positions[column.field] < len(row)
            else _default(column.kind)
            for column in spec.columns
        }
        records.append(spec.model(**values, ref=SourceRef(file_name, spec.tab, row_number)))
    return records


def _locate_columns(rows: Iterator[tuple[int, Row]], spec: SheetSpec) -> dict[str, int]:
    """Advance ``rows`` past the header row and return the position of each known column."""
    wanted = {schema.normalize_header(c.header): c for c in spec.columns}
    for _, (_, row) in zip(range(HEADER_SEARCH_ROWS), rows, strict=False):
        headers = [schema.normalize_header(cell) for cell in row]
        if schema.normalize_header(spec.anchor) not in headers:
            continue
        positions = {wanted[h].field: i for i, h in enumerate(headers) if h in wanted}
        missing = [c.header for c in spec.columns if c.required and c.field not in positions]
        if missing:
            raise SchemaError(f"Aba {spec.tab}: coluna(s) não encontrada(s): {', '.join(missing)}")
        return positions
    raise SchemaError(f"Aba {spec.tab}: cabeçalho não encontrado")


def _convert(value: Any, kind: Kind) -> Any:
    match kind:
        case Kind.DATE:
            return value.date() if isinstance(value, datetime) else value
        case Kind.TEXT:
            return _text(value)
        case Kind.INTEGER:
            return int(_number(value))
        case Kind.NUMBER:
            return _number(value)


def _default(kind: Kind) -> Any:
    return {Kind.DATE: None, Kind.TEXT: "", Kind.INTEGER: 0, Kind.NUMBER: 0.0}[kind]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _number(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
