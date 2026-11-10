"""Domain records parsed from the workbooks.

``period`` is the payroll period ("competência"), labelled like ``SET/2026`` and running
from the 26th of the previous month to the 25th.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Where a record lives in the workbooks, so a finding can point the user to it."""

    file: str
    tab: str
    row: int

    def __str__(self) -> str:
        return f"{self.file} · aba {self.tab} · linha {self.row}"


@dataclass(slots=True)
class Freight:
    date: date
    invoice: str
    driver: str
    plate: str
    origin: str
    customer: str
    destination: str
    material: str
    weight_t: float
    gross_rate: float
    net_rate: float
    status: str
    commissionable: str
    notes: str
    period: str
    gross_revenue: float
    net_revenue: float
    withholding: float
    commission_rate: float
    commission: float
    alert: str
    ref: SourceRef | None = None


@dataclass(slots=True)
class FuelEntry:
    date: date
    plate: str
    driver: str
    station: str
    fuel_type: str
    receipt: str
    odometer_km: float
    liters: float
    total: float
    payment_method: str
    notes: str
    period: str
    price_per_liter: float
    km_driven: float
    km_per_liter: float
    alert: str
    ref: SourceRef | None = None


@dataclass(slots=True)
class TollEntry:
    date: date
    plate: str
    driver: str
    plaza: str
    axles: float
    amount: float
    payment_method: str
    freight_invoice: str
    notes: str
    highway: str
    period: str
    alert: str
    ref: SourceRef | None = None


@dataclass(slots=True)
class PayrollAdjustment:
    period: str
    driver: str
    kind: str
    amount: float
    notes: str
    source_tab: str
    ref: SourceRef | None = None


@dataclass(slots=True)
class PayrollSummary:
    driver: str
    plate: str
    trips: int
    tonnes: float
    gross_revenue: float
    net_revenue: float
    commissionable_revenue: float
    commission_rate: float
    commission: float
    inss: float
    health_plan: float
    meal_voucher: float
    advance: float
    salary: float
    bonus: float
    union_fee: float
    loan: float
    gravel_trips: float
    road_train: float
    fixed_amount: float
    other: float
    total_adjustments: float
    total_pay: float
    period: str = ""
    ref: SourceRef | None = None


@dataclass(slots=True)
class VehicleResult:
    plate: str
    driver: str
    trips: int
    tonnes: float
    gross_revenue: float
    net_revenue: float
    commission: float
    liters: float
    fuel: float
    km_driven: float
    km_per_liter: float
    toll: float
    operating_result: float
    margin: float
    cost_ratio: float
    period: str = ""
    ref: SourceRef | None = None


class FileStatus(StrEnum):
    OK = "ok"
    IGNORED = "ignored"
    ERROR = "error"


@dataclass(slots=True)
class WorkbookData:
    """Everything read from a single workbook file."""

    path: str
    status: FileStatus
    reason: str = ""
    modified_at: datetime | None = None
    freights: list[Freight] = field(default_factory=list)
    fuel: list[FuelEntry] = field(default_factory=list)
    tolls: list[TollEntry] = field(default_factory=list)
    adjustments: list[PayrollAdjustment] = field(default_factory=list)
    payroll: list[PayrollSummary] = field(default_factory=list)
    vehicles: list[VehicleResult] = field(default_factory=list)


@dataclass(slots=True)
class SourceFile:
    """How one workbook of the data source was handled, for display in the settings page."""

    name: str
    status: FileStatus
    reason: str
    freights: int
    duplicated_freights: int
    modified_at: datetime | None


@dataclass(slots=True)
class Dataset:
    """All workbooks of the data source merged together."""

    freights: list[Freight]
    fuel: list[FuelEntry]
    tolls: list[TollEntry]
    adjustments: list[PayrollAdjustment]
    payroll: list[PayrollSummary]
    vehicles: list[VehicleResult]
    files: list[SourceFile]
    periods: list[str]
    drivers: list[str]
    customers: list[str]
    materials: list[str]
    loaded_at: datetime
    last_modified: datetime | None

    @property
    def workbook_count(self) -> int:
        return sum(1 for f in self.files if f.status is FileStatus.OK)

    @property
    def duplicated_freights(self) -> int:
        return sum(f.duplicated_freights for f in self.files)


def empty_dataset() -> Dataset:
    """A dataset with no records, for showing the pages when nothing could be loaded."""
    return Dataset([], [], [], [], [], [], [], [], [], [], [], datetime.now(), None)
