"""Layout of the company workbook: tab names and the header text of each column.

The workbook is written in Brazilian Portuguese, so header texts stay in Portuguese and are
mapped to English field names. Columns are located by header text, not by position, so
reordering or inserting columns in the workbook does not break the import.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from fleetdesk.data.models import (
    Freight,
    FuelEntry,
    PayrollAdjustment,
    PayrollSummary,
    TollEntry,
    VehicleResult,
)


class Kind(Enum):
    DATE = "date"
    TEXT = "text"
    NUMBER = "number"
    INTEGER = "integer"


@dataclass(frozen=True, slots=True)
class Column:
    header: str
    field: str
    kind: Kind = Kind.NUMBER
    required: bool = True


@dataclass(frozen=True, slots=True)
class SheetSpec:
    tab: str
    model: type[Any]
    columns: tuple[Column, ...]
    #: Rows whose first column is not a date are skipped (subtotals, blank form rows).
    date_rows_only: bool = False
    #: Rows whose first cell equals one of these values are skipped (e.g. the TOTAL line).
    skip_first_cell: tuple[str, ...] = ()

    @property
    def anchor(self) -> str:
        """Header text of the first column, used to find the header row."""
        return self.columns[0].header


def normalize_header(value: object) -> str:
    return " ".join(str(value).split()).upper() if value is not None else ""


DATE, TEXT, INT = Kind.DATE, Kind.TEXT, Kind.INTEGER

FREIGHTS = SheetSpec(
    tab="LANÇAMENTOS",
    model=Freight,
    date_rows_only=True,
    columns=(
        Column("DATA", "date", DATE),
        Column("Nº NF", "invoice", TEXT),
        Column("MOTORISTA", "driver", TEXT),
        Column("PLACA", "plate", TEXT),
        Column("LOCAL DE CARREGAMENTO (ORIGEM)", "origin", TEXT),
        Column("EMPRESA (CLIENTE)", "customer", TEXT),
        Column("LOCAL DE DESCARGA (DESTINO)", "destination", TEXT),
        Column("MATERIAL", "material", TEXT),
        Column("PESO (T)", "weight_t"),
        Column("VALOR BRUTO (R$/T)", "gross_rate"),
        Column("VALOR LÍQUIDO (R$/T)", "net_rate"),
        Column("SITUAÇÃO", "status", TEXT, required=False),
        Column("COMISSIONA? (SIM/NÃO)", "commissionable", TEXT, required=False),
        Column("OBSERVAÇÕES", "notes", TEXT, required=False),
        Column("COMPETÊNCIA", "period", TEXT),
        Column("FATURAMENTO BRUTO (R$)", "gross_revenue"),
        Column("PRODUÇÃO LÍQUIDA (R$)", "net_revenue"),
        Column("RETENÇÃO / IMPOSTO (R$)", "withholding", required=False),
        Column("% COMISSÃO", "commission_rate", required=False),
        Column("COMISSÃO (R$)", "commission"),
        Column("ALERTA", "alert", TEXT, required=False),
    ),
)

FUEL = SheetSpec(
    tab="COMBUSTÍVEL",
    model=FuelEntry,
    date_rows_only=True,
    columns=(
        Column("DATA", "date", DATE),
        Column("PLACA", "plate", TEXT),
        Column("MOTORISTA", "driver", TEXT),
        Column("POSTO", "station", TEXT, required=False),
        Column("TIPO DE COMBUSTÍVEL", "fuel_type", TEXT, required=False),
        Column("Nº NOTA / CUPOM", "receipt", TEXT, required=False),
        Column("KM DO HODÔMETRO", "odometer_km", required=False),
        Column("LITROS", "liters"),
        Column("VALOR TOTAL (R$)", "total"),
        Column("FORMA DE PAGAMENTO", "payment_method", TEXT, required=False),
        Column("OBSERVAÇÕES", "notes", TEXT, required=False),
        Column("COMPETÊNCIA", "period", TEXT),
        Column("R$ / LITRO", "price_per_liter", required=False),
        Column("KM RODADO (DESDE O ABASTECIMENTO ANTERIOR)", "km_driven", required=False),
        Column("KM / LITRO", "km_per_liter", required=False),
        Column("ALERTA", "alert", TEXT, required=False),
    ),
)

TOLLS = SheetSpec(
    tab="PEDÁGIO",
    model=TollEntry,
    date_rows_only=True,
    columns=(
        Column("DATA", "date", DATE),
        Column("PLACA", "plate", TEXT),
        Column("MOTORISTA", "driver", TEXT),
        Column("PRAÇA DE PEDÁGIO", "plaza", TEXT, required=False),
        Column("Nº DE EIXOS", "axles", required=False),
        Column("VALOR (R$)", "amount"),
        Column("FORMA DE PAGAMENTO", "payment_method", TEXT, required=False),
        Column("Nº NF DO FRETE (OPCIONAL)", "freight_invoice", TEXT, required=False),
        Column("OBSERVAÇÕES", "notes", TEXT, required=False),
        Column("RODOVIA", "highway", TEXT, required=False),
        Column("COMPETÊNCIA", "period", TEXT),
        Column("ALERTA", "alert", TEXT, required=False),
    ),
)

ADJUSTMENTS = SheetSpec(
    tab="AJUSTES FOLHA",
    model=PayrollAdjustment,
    columns=(
        Column("COMPETÊNCIA", "period", TEXT),
        Column("MOTORISTA", "driver", TEXT),
        Column("TIPO", "kind", TEXT),
        Column("VALOR (R$)", "amount"),
        Column("OBSERVAÇÃO", "notes", TEXT, required=False),
        Column("ABA ORIGINAL", "source_tab", TEXT, required=False),
    ),
)

PAYROLL = SheetSpec(
    tab="FECHAMENTO",
    model=PayrollSummary,
    skip_first_cell=("TOTAL",),
    columns=(
        Column("MOTORISTA", "driver", TEXT),
        Column("PLACA PRINCIPAL", "plate", TEXT, required=False),
        Column("VIAGENS", "trips", INT),
        Column("TONELADAS", "tonnes"),
        Column("FATURAMENTO BRUTO", "gross_revenue"),
        Column("PRODUÇÃO LÍQUIDA", "net_revenue"),
        Column("PRODUÇÃO COMISSIONADA", "commissionable_revenue", required=False),
        Column("% COM.", "commission_rate", required=False),
        Column("COMISSÃO", "commission"),
        Column("INSS", "inss", required=False),
        Column("UNIMED", "health_plan", required=False),
        Column("TICKET ALIMENTAÇÃO", "meal_voucher", required=False),
        Column("ADIANTAMENTO", "advance", required=False),
        Column("SALÁRIO", "salary", required=False),
        Column("GRATIFICAÇÃO", "bonus", required=False),
        Column("CONTRIBUIÇÃO SINDICAL", "union_fee", required=False),
        Column("EMPRÉSTIMO", "loan", required=False),
        Column("CASCALHO (VIAGENS)", "gravel_trips", required=False),
        Column("RODOTREM", "road_train", required=False),
        Column("VALOR FIXO", "fixed_amount", required=False),
        Column("OUTROS", "other", required=False),
        Column("TOTAL AJUSTES", "total_adjustments"),
        Column("SALÁRIO TOTAL", "total_pay"),
    ),
)

VEHICLES = SheetSpec(
    tab="RESULTADO POR PLACA",
    model=VehicleResult,
    columns=(
        Column("PLACA", "plate", TEXT),
        Column("MOTORISTA PRINCIPAL", "driver", TEXT, required=False),
        Column("VIAGENS", "trips", INT),
        Column("TONELADAS", "tonnes"),
        Column("FATURAMENTO BRUTO", "gross_revenue"),
        Column("PRODUÇÃO LÍQUIDA", "net_revenue"),
        Column("COMISSÃO", "commission"),
        Column("LITROS", "liters", required=False),
        Column("COMBUSTÍVEL", "fuel", required=False),
        Column("KM RODADO", "km_driven", required=False),
        Column("KM / LITRO", "km_per_liter", required=False),
        Column("PEDÁGIO", "toll", required=False),
        Column("RESULTADO OPERACIONAL", "operating_result", required=False),
        Column("MARGEM %", "margin", required=False),
        Column("COMB.+PED. / PRODUÇÃO", "cost_ratio", required=False),
    ),
)

#: The tab that identifies a workbook as a supported freight workbook.
IDENTIFYING_TAB = FREIGHTS.tab
