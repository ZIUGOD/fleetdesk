from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook

from fleetdesk.data import schema
from fleetdesk.data.models import FileStatus
from fleetdesk.data.workbook import SchemaError, read_workbook
from fleetdesk.sample_data import DRIVERS, write_sheet
from tests.conftest import SAMPLE_TRIPS

FREIGHT = {
    "date": date(2026, 9, 1),
    "invoice": 123.0,
    "driver": "ANA",
    "plate": "ABC1D23",
    "origin": "A",
    "customer": "C",
    "destination": "D",
    "material": "BRITA",
    "weight_t": 30,
    "gross_rate": 10,
    "net_rate": 8,
    "period": "SET/2026",
    "gross_revenue": 300,
    "net_revenue": 240,
    "commission": 24,
}


def _save(workbook: Workbook, path: Path) -> Path:
    del workbook["Sheet"]
    workbook.save(path)
    return path


def test_reads_every_tab_of_the_sample_workbook(sample_workbook: Path) -> None:
    data = read_workbook(str(sample_workbook))

    assert data.status is FileStatus.OK
    assert len(data.freights) == SAMPLE_TRIPS
    assert {f.period for f in data.freights} == {"SET/2026"}
    assert len(data.payroll) == len(DRIVERS)  # the TOTAL row is skipped
    assert len(data.vehicles) == len(DRIVERS)
    assert data.fuel and data.tolls and data.adjustments


def test_payroll_and_vehicles_inherit_the_main_freight_period(sample_workbook: Path) -> None:
    data = read_workbook(str(sample_workbook))

    assert {p.period for p in data.payroll} == {"SET/2026"}
    assert {v.period for v in data.vehicles} == {"SET/2026"}


def test_columns_are_found_by_header_regardless_of_order(tmp_path: Path) -> None:
    headers = [c.header for c in reversed(schema.FREIGHTS.columns)]
    workbook = Workbook()
    write_sheet(workbook, schema.FREIGHTS, [FREIGHT], headers=headers)
    data = read_workbook(str(_save(workbook, tmp_path / "reordered.xlsx")))

    freight = data.freights[0]
    assert (freight.driver, freight.weight_t, freight.net_revenue) == ("ANA", 30.0, 240.0)
    assert freight.invoice == "123"  # whole floats lose the ".0"
    assert freight.date == date(2026, 9, 1)


def test_optional_columns_may_be_missing(tmp_path: Path) -> None:
    required = [c.header for c in schema.FREIGHTS.columns if c.required]
    workbook = Workbook()
    write_sheet(workbook, schema.FREIGHTS, [FREIGHT], headers=required)
    data = read_workbook(str(_save(workbook, tmp_path / "minimal.xlsx")))

    assert data.freights[0].alert == ""
    assert data.freights[0].withholding == 0.0


def test_missing_required_column_is_reported(tmp_path: Path) -> None:
    headers = [c.header for c in schema.FREIGHTS.columns if c.header != "PESO (T)"]
    workbook = Workbook()
    write_sheet(workbook, schema.FREIGHTS, [FREIGHT], headers=headers)

    with pytest.raises(SchemaError, match="PESO"):
        read_workbook(str(_save(workbook, tmp_path / "broken.xlsx")))


def test_rows_without_a_date_are_skipped(tmp_path: Path) -> None:
    workbook = Workbook()
    write_sheet(workbook, schema.FREIGHTS, [FREIGHT, {**FREIGHT, "date": "SUBTOTAL"}])
    data = read_workbook(str(_save(workbook, tmp_path / "subtotal.xlsx")))

    assert len(data.freights) == 1


def test_workbook_in_another_format_is_ignored(tmp_path: Path) -> None:
    workbook = Workbook()
    workbook.active.title = "MOTORISTA 1"  # type: ignore[union-attr]
    path = tmp_path / "old-format.xlsx"
    workbook.save(path)

    data = read_workbook(str(path))

    assert data.status is FileStatus.IGNORED
    assert "LANÇAMENTOS" in data.reason
