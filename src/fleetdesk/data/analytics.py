"""Indicators and chart series computed from the merged dataset."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol, TypeVar

from fleetdesk.data.models import Freight, FuelEntry, PayrollAdjustment, PayrollSummary, TollEntry

OTHERS_LABEL = "Outros"
UNKNOWN_LABEL = "(sem info)"


class HasPeriod(Protocol):
    period: str


P = TypeVar("P", bound=HasPeriod)


def in_period(records: Iterable[P], period: str) -> list[P]:
    """Records of one payroll period; an empty period means all of them."""
    return [r for r in records if r.period == period] if period else list(records)


@dataclass(frozen=True, slots=True)
class Kpis:
    trips: int
    tonnes: float
    gross_revenue: float
    net_revenue: float
    commission: float
    fuel: float
    tolls: float
    payroll_total: float
    #: Net revenue minus commissions, fuel and tolls.
    operating_result: float
    net_per_tonne: float
    average_ticket: float
    withholding: float
    withholding_share: float
    operating_margin: float


def compute_kpis(
    freights: Sequence[Freight],
    payroll: Iterable[PayrollSummary],
    fuel: Iterable[FuelEntry],
    tolls: Iterable[TollEntry],
) -> Kpis:
    tonnes = sum(f.weight_t for f in freights)
    gross = sum(f.gross_revenue for f in freights)
    net = sum(f.net_revenue for f in freights)
    commission = sum(f.commission for f in freights)
    fuel_total = sum(e.total for e in fuel)
    toll_total = sum(e.amount for e in tolls)
    result = net - commission - fuel_total - toll_total
    return Kpis(
        trips=len(freights),
        tonnes=tonnes,
        gross_revenue=gross,
        net_revenue=net,
        commission=commission,
        fuel=fuel_total,
        tolls=toll_total,
        payroll_total=sum(p.total_pay for p in payroll),
        operating_result=result,
        net_per_tonne=_ratio(net, tonnes),
        average_ticket=_ratio(gross, len(freights)),
        withholding=gross - net,
        withholding_share=_ratio(gross - net, gross),
        operating_margin=_ratio(result, net),
    )


@dataclass(frozen=True, slots=True)
class Series:
    labels: list[str]
    values: list[float]


def totals_by(
    records: Iterable[Any],
    key: str,
    value: str,
    limit: int | None = None,
    fold_rest: bool = False,
) -> Series:
    """Sum ``value`` per distinct ``key``, largest first.

    With ``limit``, only the top entries are kept; ``fold_rest`` adds the remainder as a
    single "Outros (n)" entry instead of dropping it.
    """
    totals: defaultdict[str, float] = defaultdict(float)
    for record in records:
        totals[getattr(record, key) or UNKNOWN_LABEL] += getattr(record, value)
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    if limit is not None and len(ranked) > limit:
        rest = ranked[limit:]
        ranked = ranked[:limit]
        if fold_rest:
            ranked.append((f"{OTHERS_LABEL} ({len(rest)})", sum(v for _, v in rest)))
    return Series(labels=[k for k, _ in ranked], values=[round(v, 2) for _, v in ranked])


@dataclass(frozen=True, slots=True)
class DailySeries:
    labels: list[str]
    gross_revenue: list[float]
    net_revenue: list[float]
    trips: list[int]


def daily_series(freights: Iterable[Freight]) -> DailySeries:
    by_day: defaultdict[date, list[float]] = defaultdict(lambda: [0.0, 0.0, 0])
    for f in freights:
        day = by_day[f.date]
        day[0] += f.gross_revenue
        day[1] += f.net_revenue
        day[2] += 1
    ordered = sorted(by_day.items())
    return DailySeries(
        labels=[d.strftime("%d/%m") for d, _ in ordered],
        gross_revenue=[round(v[0], 2) for _, v in ordered],
        net_revenue=[round(v[1], 2) for _, v in ordered],
        trips=[int(v[2]) for _, v in ordered],
    )


@dataclass(slots=True)
class DriverStatement:
    """What a driver produced in a period, next to the payroll adjustments made to them."""

    driver: str
    trips: int = 0
    gross_revenue: float = 0.0
    net_revenue: float = 0.0
    commission: float = 0.0
    #: Fuel and tolls recorded under the driver's name.
    trip_costs: float = 0.0
    deductions: float = 0.0
    additions: float = 0.0

    @property
    def adjustments(self) -> float:
        return self.deductions + self.additions

    @property
    def commission_after_adjustments(self) -> float:
        return self.commission + self.adjustments


def driver_statements(
    freights: Iterable[Freight],
    adjustments: Iterable[PayrollAdjustment],
    fuel: Iterable[FuelEntry] = (),
    tolls: Iterable[TollEntry] = (),
) -> list[DriverStatement]:
    """One statement per driver who travelled or had an adjustment, highest revenue first."""
    statements: dict[str, DriverStatement] = {}

    def of(driver: str) -> DriverStatement:
        return statements.setdefault(driver, DriverStatement(driver))

    for f in freights:
        s = of(f.driver)
        s.trips += 1
        s.gross_revenue += f.gross_revenue
        s.net_revenue += f.net_revenue
        s.commission += f.commission
    for a in adjustments:
        s = of(a.driver)
        if a.amount < 0:
            s.deductions += a.amount
        else:
            s.additions += a.amount
    for e in fuel:
        of(e.driver).trip_costs += e.total
    for t in tolls:
        of(t.driver).trip_costs += t.amount

    statements.pop("", None)
    return sorted(statements.values(), key=lambda s: (-s.gross_revenue, s.driver))


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
