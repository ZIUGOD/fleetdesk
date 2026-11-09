from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from fleetdesk.data import analytics
from fleetdesk.data.models import Freight, FuelEntry, PayrollAdjustment, PayrollSummary, TollEntry


def freight(**overrides: Any) -> Freight:
    values: dict[str, Any] = {
        "date": date(2026, 9, 1),
        "invoice": "1",
        "driver": "ANA",
        "plate": "AAA1A11",
        "origin": "O",
        "customer": "C",
        "destination": "D",
        "material": "M",
        "weight_t": 10.0,
        "gross_rate": 10.0,
        "net_rate": 8.0,
        "status": "",
        "commissionable": "SIM",
        "notes": "",
        "period": "SET/2026",
        "gross_revenue": 100.0,
        "net_revenue": 80.0,
        "withholding": 20.0,
        "commission_rate": 0.1,
        "commission": 8.0,
        "alert": "OK",
    }
    return Freight(**{**values, **overrides})


def test_kpis_combine_freights_and_costs() -> None:
    fuel = FuelEntry(
        date(2026, 9, 1), "AAA1A11", "ANA", "", "", "", 0, 10, 12.0, "", "", "SET/2026", 0, 0, 0, ""
    )
    toll = TollEntry(date(2026, 9, 1), "AAA1A11", "ANA", "", 6, 4.0, "", "", "", "", "SET/2026", "")
    payroll = PayrollSummary("ANA", "", 2, 20, 200, 160, 160, 0.1, 16, *([0.0] * 12), 0, 150.0)

    kpis = analytics.compute_kpis([freight(), freight()], [payroll], [fuel], [toll])

    assert kpis.trips == 2
    assert kpis.gross_revenue == 200
    assert kpis.operating_result == 160 - 16 - 12 - 4
    assert kpis.operating_margin == pytest.approx(128 / 160)
    assert kpis.withholding_share == pytest.approx(0.2)
    assert kpis.net_per_tonne == 8
    assert kpis.payroll_total == 150


def test_kpis_of_an_empty_selection_do_not_divide_by_zero() -> None:
    kpis = analytics.compute_kpis([], [], [], [])
    assert (kpis.average_ticket, kpis.net_per_tonne, kpis.operating_margin) == (0, 0, 0)


def test_totals_by_ranks_and_folds_the_tail() -> None:
    rows = [
        freight(driver=name, net_revenue=value)
        for name, value in [("A", 50), ("B", 30), ("A", 10), ("C", 5), ("D", 1)]
    ]

    series = analytics.totals_by(rows, "driver", "net_revenue", limit=2, fold_rest=True)

    assert series.labels == ["A", "B", "Outros (2)"]
    assert series.values == [60, 30, 6]


def test_totals_by_labels_blank_keys() -> None:
    series = analytics.totals_by([freight(customer="")], "customer", "gross_revenue")
    assert series.labels == [analytics.UNKNOWN_LABEL]


def test_daily_series_is_chronological_across_months() -> None:
    rows = [
        freight(date=date(2026, 9, 1)),
        freight(date=date(2026, 8, 28)),
        freight(date=date(2026, 9, 1)),
    ]

    series = analytics.daily_series(rows)

    assert series.labels == ["28/08", "01/09"]
    assert series.trips == [1, 2]


def test_driver_statements_put_revenue_next_to_adjustments() -> None:
    def adjustment(driver: str, amount: float) -> PayrollAdjustment:
        return PayrollAdjustment("SET/2026", driver, "TIPO", amount, "", "")

    fuel = FuelEntry(
        date(2026, 9, 1), "AAA1A11", "ANA", "", "", "", 0, 10, 12.0, "", "", "SET/2026", 0, 0, 0, ""
    )
    statements = analytics.driver_statements(
        [freight(driver="ANA"), freight(driver="ANA"), freight(driver="BIA", gross_revenue=50)],
        [adjustment("ANA", -30), adjustment("ANA", 10), adjustment("CAIO", -5)],
        [fuel],
    )

    ana, bia, caio = statements  # highest revenue first; CAIO only has an adjustment
    assert (ana.driver, ana.trips, ana.gross_revenue, ana.commission) == ("ANA", 2, 200, 16)
    assert (ana.deductions, ana.additions, ana.trip_costs) == (-30, 10, 12)
    assert ana.commission_after_adjustments == 16 - 30 + 10
    assert (bia.driver, bia.adjustments) == ("BIA", 0)
    assert (caio.driver, caio.trips, caio.deductions) == ("CAIO", 0, -5)


def test_in_period_keeps_everything_when_no_period_is_selected() -> None:
    rows = [freight(period="AGO/2026"), freight(period="SET/2026")]
    assert analytics.in_period(rows, "") == rows
    assert analytics.in_period(rows, "AGO/2026") == rows[:1]
