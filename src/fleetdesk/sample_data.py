"""Generate realistic but entirely fictitious workbooks in the company's format.

Used by the test suite and for demos, so no real company data ever needs to leave the
client's machine. Run ``python -m fleetdesk.sample_data <folder> --months 3``.
"""

from __future__ import annotations

import argparse
import random
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from fleetdesk.data import schema
from fleetdesk.data.schema import SheetSpec

MONTHS = ("JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ")

DRIVERS = (
    "ANDRÉ",
    "BRUNO",
    "CARLOS",
    "DANIEL",
    "EDSON",
    "FÁBIO",
    "GILBERTO",
    "HÉLIO",
    "IVAN",
    "JORGE",
    "LUCAS",
    "MÁRCIO",
    "NELSON",
    "OTÁVIO",
    "SÉRGIO",
    "RENATO",
)
CUSTOMERS = (
    "CONSTRUTORA HORIZONTE",
    "MINERAÇÃO SERRA AZUL",
    "PAVIMENTA BR",
    "CONCRETO FORTE",
    "URBANIZA",
    "ASFALTO NORTE",
    "OBRAS VALE",
    "CIMENTEC",
)
ORIGINS = ("PEDREIRA VALE VERDE", "PEDREIRA SÃO JOSÉ", "AREAL DO RIO", "JAZIDA BOA VISTA")
DESTINATIONS = (
    "USINA DE ASFALTO",
    "CANTEIRO BR-040",
    "PÁTIO CENTRAL",
    "OBRA ANEL VIÁRIO",
    "KM 214",
)
MATERIALS = (
    "BRITA 1",
    "PÓ DE BRITA",
    "AREIA LAVADA",
    "CASCALHO",
    "RACHÃO",
    "PEDRA MARROADA",
    "BGS",
)
STATIONS = ("POSTO ESTRELA", "POSTO RODOVIA", "AUTO POSTO 040")
PLAZAS = (("PRAÇA NORTE", "BR-040"), ("PRAÇA SUL", "BR-381"))
#: Payroll adjustment kind -> (payroll field, signed amount range).
ADJUSTMENT_KINDS: dict[str, tuple[str, tuple[float, float]]] = {
    "VALOR FIXO": ("fixed_amount", (2600, 3200)),
    "INSS": ("inss", (-320, -210)),
    "TICKET ALIMENTAÇÃO": ("meal_voucher", (-600, -600)),
    "ADIANTAMENTO": ("advance", (-1600, -800)),
    "GRATIFICAÇÃO": ("bonus", (150, 500)),
}

ROUTE_COUNT = 24

#: Rows above the header, mimicking the title block of the real workbook.
TITLE_ROWS = 3


def period_label(year: int, month: int) -> str:
    return f"{MONTHS[month - 1]}/{year}"


def period_dates(year: int, month: int) -> list[date]:
    """A period runs from the 26th of the previous month to the 25th of ``month``."""
    start = date(year - 1, 12, 26) if month == 1 else date(year, month - 1, 26)
    end = date(year, month, 25)
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def write_sheet(
    workbook: Workbook,
    spec: SheetSpec,
    rows: Iterable[dict[str, Any]],
    headers: Sequence[str] | None = None,
) -> Worksheet:
    """Write ``rows`` (keyed by field name) under ``headers`` (defaults to the spec's order)."""
    sheet: Worksheet = workbook.create_sheet(spec.tab)
    sheet.append([f"{spec.tab} — planilha de exemplo"])
    for _ in range(TITLE_ROWS - 1):
        sheet.append([])
    by_header = {c.header: c.field for c in spec.columns}
    header_list = list(headers or by_header)
    sheet.append(header_list)
    for row in rows:
        sheet.append([row.get(by_header.get(h, ""), None) for h in header_list])
    return sheet


def build_workbook(
    path: Path,
    year: int,
    month: int,
    trips: int = 450,
    seed: int = 7,
    mistakes: bool = False,
) -> Path:
    rng = random.Random(f"{seed}-{year}-{month}")
    period = period_label(year, month)
    days = [d for d in period_dates(year, month) if d.weekday() < 6]
    fleet = {driver: _plate(rng) for driver in DRIVERS}

    # Like a real fleet, a couple dozen recurring routes, each with its own negotiated rate
    # (the same every month) and small trip-to-trip variation.
    route_rng = random.Random(seed)
    routes = [
        (
            route_rng.choices(CUSTOMERS, weights=(9, 7, 5, 4, 3, 2, 2, 1))[0],
            route_rng.choice(MATERIALS),
            route_rng.choice(ORIGINS),
            route_rng.choice(DESTINATIONS),
        )
        for _ in range(ROUTE_COUNT)
    ]
    route_rates = {route: round(route_rng.uniform(22, 48), 2) for route in routes}
    route_weights = [route_rng.uniform(1, 6) for _ in routes]

    freights = []
    for _ in range(trips):
        driver = rng.choice(DRIVERS)
        route = rng.choices(routes, weights=route_weights)[0]
        freights.append(
            _freight(
                rng.choice(days),
                rng.randint(1000, 99999),
                driver,
                fleet[driver],
                route,
                weight=round(rng.uniform(34, 52), 2),
                gross_rate=round(route_rates[route] * rng.uniform(0.97, 1.03), 2),
                net_ratio=rng.uniform(0.76, 0.84),
                commissionable=rng.random() > 0.1,
                period=period,
            )
        )
    freights.sort(key=lambda f: (f["date"], f["driver"]))

    fuel = []
    for driver, plate in fleet.items():
        odometer = rng.randint(80_000, 400_000)
        for day in sorted(rng.sample(days, 4)):
            km = rng.randint(700, 1500)
            liters = round(km / rng.uniform(2.2, 3.2), 1)
            odometer += km
            price = round(rng.uniform(5.9, 6.4), 2)
            fuel.append(
                {
                    "date": day,
                    "plate": plate,
                    "driver": driver,
                    "station": rng.choice(STATIONS),
                    "fuel_type": "DIESEL S10",
                    "odometer_km": odometer,
                    "liters": liters,
                    "total": round(liters * price, 2),
                    "payment_method": "CARTÃO FROTA",
                    "period": period,
                    "price_per_liter": price,
                    "km_driven": km,
                    "km_per_liter": round(km / liters, 2),
                    "alert": "OK",
                }
            )

    tolls = []
    for driver, plate in fleet.items():
        for day in rng.sample(days, 6):
            plaza, highway = rng.choice(PLAZAS)
            tolls.append(
                {
                    "date": day,
                    "plate": plate,
                    "driver": driver,
                    "plaza": plaza,
                    "axles": 6,
                    "amount": round(rng.uniform(40, 95), 2),
                    "payment_method": "TAG",
                    "highway": highway,
                    "period": period,
                    "alert": "OK",
                }
            )

    adjustments = []
    for driver in DRIVERS:
        for kind, (_, (low, high)) in ADJUSTMENT_KINDS.items():
            if kind == "GRATIFICAÇÃO" and rng.random() < 0.6:
                continue
            adjustments.append(
                {
                    "period": period,
                    "driver": driver,
                    "kind": kind,
                    "amount": round(rng.uniform(low, high), 2),
                    "source_tab": "EXEMPLO",
                }
            )

    if mistakes:
        _plant_mistakes(rng, freights, adjustments)
    payroll = _payroll(freights, adjustments, fleet)
    vehicles = _vehicles(freights, fuel, tolls, fleet)

    workbook = Workbook()
    workbook.remove(workbook.active)  # type: ignore[arg-type]
    write_sheet(workbook, schema.FREIGHTS, freights)
    write_sheet(workbook, schema.FUEL, fuel)
    write_sheet(workbook, schema.TOLLS, tolls)
    write_sheet(workbook, schema.ADJUSTMENTS, adjustments)
    # The real workbook has one extra title row above these two tables (header on row 5).
    write_sheet(workbook, schema.PAYROLL, payroll).insert_rows(1)
    write_sheet(workbook, schema.VEHICLES, vehicles).insert_rows(1)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path


def _freight(
    day: date,
    invoice: int,
    driver: str,
    plate: str,
    route: tuple[str, str, str, str],
    *,
    weight: float,
    gross_rate: float,
    net_ratio: float,
    commissionable: bool,
    period: str,
) -> dict[str, Any]:
    customer, material, origin, destination = route
    net_rate = round(gross_rate * net_ratio, 2)
    net = round(weight * net_rate, 2)
    return {
        "date": day,
        "invoice": invoice,
        "driver": driver,
        "plate": plate,
        "origin": origin,
        "customer": customer,
        "destination": destination,
        "material": material,
        "weight_t": weight,
        "gross_rate": gross_rate,
        "net_rate": net_rate,
        "status": "ENTREGUE",
        "commissionable": "SIM" if commissionable else "NÃO",
        "period": period,
        "gross_revenue": round(weight * gross_rate, 2),
        "net_revenue": net,
        "withholding": round(weight * (gross_rate - net_rate), 2),
        "commission_rate": 0.10 if commissionable else 0,
        "commission": round(net * 0.10, 2) if commissionable else 0,
        "alert": "OK",
    }


#: Audit finding codes that ``build_workbook(mistakes=True)`` deliberately triggers.
PLANTED_MISTAKES = ("weight_typo", "rate_outlier", "similar_names", "adjustment_sign")


def _replace(freights: list[dict[str, Any]], index: int, **changes: Any) -> None:
    """Rebuild a freight with some inputs changed, keeping its totals consistent."""
    f = {**freights[index], **changes}
    freights[index] = _freight(
        f["date"],
        f["invoice"],
        f["driver"],
        f["plate"],
        (f["customer"], f["material"], f["origin"], f["destination"]),
        weight=f["weight_t"],
        gross_rate=f["gross_rate"],
        net_ratio=f["net_rate"] / freights[index]["gross_rate"],
        commissionable=f["commissionable"] == "SIM",
        period=f["period"],
    )


def _plant_mistakes(
    rng: random.Random, freights: list[dict[str, Any]], adjustments: list[dict[str, Any]]
) -> None:
    """Typical data-entry mistakes, so demos and tests show the audit at work."""

    # Plant them on the busiest route, where the audit has enough trips to know "normal".
    def route(f: dict[str, Any]) -> tuple[str, ...]:
        return (f["customer"], f["material"], f["origin"], f["destination"])

    busiest = Counter(route(f) for f in freights).most_common(1)[0][0]
    candidates = [i for i, f in enumerate(freights) if route(f) == busiest]
    weight_pick, rate_pick = rng.sample(candidates, 2)
    # A decimal point in the wrong place: 41,30 t typed as 4,13 t.
    _replace(freights, weight_pick, weight_t=round(freights[weight_pick]["weight_t"] / 10, 2))
    # A rate typed three times too high.
    _replace(freights, rate_pick, gross_rate=round(freights[rate_pick]["gross_rate"] * 3, 2))
    # The same customer written two ways.
    main_customer = CUSTOMERS[0]
    for f in [f for f in freights if f["customer"] == main_customer][:4]:
        f["customer"] = f"{main_customer} LTDA"
    # A deduction entered as a credit.
    inss = next(a for a in adjustments if a["kind"] == "INSS")
    inss["amount"] = abs(inss["amount"])


def _plate(rng: random.Random) -> str:
    letters = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(3))
    return f"{letters}{rng.randint(0, 9)}{rng.choice('ABCDEFGHJ')}{rng.randint(10, 99)}"


def _payroll(
    freights: list[dict[str, Any]], adjustments: list[dict[str, Any]], fleet: dict[str, str]
) -> list[dict[str, Any]]:
    rows = []
    for driver in DRIVERS:
        own = [f for f in freights if f["driver"] == driver]
        commissionable = sum(f["net_revenue"] for f in own if f["commission_rate"])
        commission = round(sum(f["commission"] for f in own), 2)
        row: dict[str, Any] = {
            "driver": driver,
            "plate": fleet[driver],
            "trips": len(own),
            "tonnes": round(sum(f["weight_t"] for f in own), 2),
            "gross_revenue": round(sum(f["gross_revenue"] for f in own), 2),
            "net_revenue": round(sum(f["net_revenue"] for f in own), 2),
            "commissionable_revenue": round(commissionable, 2),
            "commission_rate": 0.10,
            "commission": commission,
        }
        total_adjustments = 0.0
        for adj in adjustments:
            if adj["driver"] == driver:
                row[ADJUSTMENT_KINDS[adj["kind"]][0]] = adj["amount"]
                total_adjustments += adj["amount"]
        row["total_adjustments"] = round(total_adjustments, 2)
        row["total_pay"] = round(commission + total_adjustments, 2)
        rows.append(row)
    rows.append({"driver": "TOTAL"})
    return rows


def _vehicles(
    freights: list[dict[str, Any]],
    fuel: list[dict[str, Any]],
    tolls: list[dict[str, Any]],
    fleet: dict[str, str],
) -> list[dict[str, Any]]:
    totals: defaultdict[str, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))
    for f in freights:
        t = totals[f["plate"]]
        t["trips"] += 1
        for key in ("weight_t", "gross_revenue", "net_revenue", "commission"):
            t[key] += f[key]
    for e in fuel:
        totals[e["plate"]]["fuel"] += e["total"]
        totals[e["plate"]]["liters"] += e["liters"]
        totals[e["plate"]]["km"] += e["km_driven"]
    for e in tolls:
        totals[e["plate"]]["toll"] += e["amount"]

    rows = []
    for driver, plate in fleet.items():
        t = totals[plate]
        result = t["net_revenue"] - t["commission"] - t["fuel"] - t["toll"]
        rows.append(
            {
                "plate": plate,
                "driver": driver,
                "trips": int(t["trips"]),
                "tonnes": round(t["weight_t"], 2),
                "gross_revenue": round(t["gross_revenue"], 2),
                "net_revenue": round(t["net_revenue"], 2),
                "commission": round(t["commission"], 2),
                "liters": round(t["liters"], 1),
                "fuel": round(t["fuel"], 2),
                "km_driven": t["km"],
                "km_per_liter": round(t["km"] / t["liters"], 2) if t["liters"] else 0,
                "toll": round(t["toll"], 2),
                "operating_result": round(result, 2),
                "margin": round(result / t["net_revenue"], 4) if t["net_revenue"] else 0,
                "cost_ratio": round((t["fuel"] + t["toll"]) / t["net_revenue"], 4)
                if t["net_revenue"]
                else 0,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate fictitious FleetDesk workbooks.")
    parser.add_argument("folder", type=Path, help="output folder (one workbook per month)")
    parser.add_argument("--months", type=int, default=3)
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--last-month", type=int, default=9, help="month of the newest period")
    parser.add_argument(
        "--clean", action="store_true", help="do not plant typical mistakes for the audit to find"
    )
    args = parser.parse_args()

    for offset in range(args.months - 1, -1, -1):
        month_index = args.last_month - 1 - offset
        year, month = args.year + month_index // 12, month_index % 12 + 1
        path = args.folder / f"{year}-{month:02d}" / f"FRETES_{MONTHS[month - 1]}_{year}.xlsx"
        build_workbook(path, year, month, mistakes=not args.clean)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
