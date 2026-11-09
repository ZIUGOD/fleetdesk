"""Rule-based and statistical checks that point out likely mistakes in the workbooks.

Every check is deterministic and explainable: each finding says why it was raised and points
to the file, tab and row to fix. The optional AI summary (``assistant.py``) only explains
these findings in plain language; it never decides what is wrong.

Thresholds were tuned on a real month of data: the workbook formulas are consistent, so what
remains are typing and data-entry mistakes (misplaced decimal points, wrong rates, the same
customer spelled two ways). User-facing text is pt-BR, like the rest of the UI.
"""

from __future__ import annotations

import statistics
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from enum import StrEnum

from fleetdesk.data.analytics import in_period
from fleetdesk.data.models import (
    Dataset,
    Freight,
    FuelEntry,
    PayrollAdjustment,
    PayrollSummary,
    SourceRef,
    TollEntry,
)
from fleetdesk.data.repository import period_sort_key
from fleetdesk.formatting import brl, number


class Severity(StrEnum):
    ERROR = "error"  # almost certainly wrong
    WARNING = "warning"  # worth checking
    INFO = "info"  # unusual, often legitimate

    @property
    def rank(self) -> int:
        return {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}[self]


@dataclass(frozen=True, slots=True)
class Issue:
    """One occurrence of a finding, as shown in its table."""

    ref: SourceRef | None
    when: date | None
    who: str
    detail: str


@dataclass(slots=True)
class Finding:
    code: str
    severity: Severity
    title: str
    #: Why this matters, in plain Portuguese.
    explanation: str
    issues: list[Issue] = field(default_factory=list)
    #: Rough amount of money at stake, when it can be estimated (R$, absolute).
    impact: float | None = None

    @property
    def count(self) -> int:
        return len(self.issues)


@dataclass(frozen=True, slots=True)
class AuditReport:
    period: str
    findings: list[Finding]
    records_checked: int

    def count(self, severity: Severity) -> int:
        return sum(1 for f in self.findings if f.severity == severity)

    @property
    def attention_count(self) -> int:
        """Findings the user should act on (errors and warnings)."""
        return self.count(Severity.ERROR) + self.count(Severity.WARNING)


# ─── thresholds ───────────────────────────────────────────────────────────────

#: A truck needs this many trips before its own weight pattern is trusted.
MIN_TRIPS_FOR_PROFILE = 8
#: Below this on a truck that usually carries 30 t or more: almost surely a typo.
TYPO_WEIGHT_T = 10.0
LOW_WEIGHT_RATIO = 0.4
HIGH_WEIGHT_RATIO = 1.5
#: A route needs this many priced trips before its usual rate is trusted.
MIN_TRIPS_FOR_ROUTE = 5
RATE_DEVIATION = 0.25
NAME_SIMILARITY = 0.85
MONEY_TOLERANCE = 1.0
KM_PER_LITER_RANGE = (1.0, 5.0)
FUEL_PRICE_DEVIATION = 0.2

DEDUCTION_KINDS = {
    "INSS",
    "UNIMED",
    "TICKET ALIMENTAÇÃO",
    "ADIANTAMENTO",
    "CONTRIBUIÇÃO SINDICAL",
    "EMPRÉSTIMO",
}
ADDITION_KINDS = {"GRATIFICAÇÃO"}


@dataclass(frozen=True, slots=True)
class _Scope:
    freights: list[Freight]
    payroll: list[PayrollSummary]
    adjustments: list[PayrollAdjustment]
    fuel: list[FuelEntry]
    tolls: list[TollEntry]


Check = Callable[[_Scope], Iterable[Finding]]


def run_audit(dataset: Dataset, period: str = "") -> AuditReport:
    scope = _Scope(
        freights=in_period(dataset.freights, period),
        payroll=in_period(dataset.payroll, period),
        adjustments=in_period(dataset.adjustments, period),
        fuel=in_period(dataset.fuel, period),
        tolls=in_period(dataset.tolls, period),
    )
    findings = [f for check in CHECKS for f in check(scope) if f.issues]
    findings.sort(key=lambda f: (f.severity.rank, -(f.impact or 0), -f.count))
    records = sum(len(x) for x in (scope.freights, scope.payroll, scope.adjustments, scope.fuel))
    return AuditReport(period=period, findings=findings, records_checked=records)


# ─── helpers ──────────────────────────────────────────────────────────────────


def _trip(f: Freight, detail: str) -> Issue:
    return Issue(f.ref, f.date, f"{f.driver} · {f.plate}", detail)


def _period_window(period: str) -> tuple[date, date] | None:
    year, month_index = period_sort_key(period)
    if not year:
        return None
    month = month_index + 1
    start = date(year - 1, 12, 26) if month == 1 else date(year, month - 1, 26)
    return start, date(year, month, 25)


def _plain(text: str) -> str:
    """Upper-case, accent-free, single-spaced: "Pó  de brita" -> "PO DE BRITA"."""
    folded = unicodedata.normalize("NFKD", text.upper())
    return " ".join("".join(c for c in folded if not unicodedata.combining(c)).split())


# ─── freight checks ───────────────────────────────────────────────────────────


def check_weights(scope: _Scope) -> list[Finding]:
    """Trips far from what the same truck usually carries (e.g. 3,58 t instead of 35,8 t)."""
    by_plate: defaultdict[str, list[Freight]] = defaultdict(list)
    for f in scope.freights:
        by_plate[f.plate].append(f)

    typos: list[Issue] = []
    unusual: list[Issue] = []
    impact = 0.0
    for trips in by_plate.values():
        if len(trips) < MIN_TRIPS_FOR_PROFILE:
            continue
        median = statistics.median(f.weight_t for f in trips)
        for f in trips:
            detail = f"{number(f.weight_t, 2)} t; este caminhão costuma levar {number(median, 1)} t"
            if f.weight_t <= 0 or (median >= 30 and f.weight_t < TYPO_WEIGHT_T):
                typos.append(_trip(f, detail))
                impact += abs(median - f.weight_t) * f.gross_rate
            elif not LOW_WEIGHT_RATIO * median <= f.weight_t <= HIGH_WEIGHT_RATIO * median:
                unusual.append(_trip(f, detail))

    return [
        Finding(
            "weight_typo",
            Severity.ERROR,
            "Peso provavelmente digitado errado",
            "Peso muito baixo para um caminhão que normalmente carrega 30 t ou mais. Costuma ser "
            "vírgula no lugar errado (3,58 em vez de 35,8). Como o peso multiplica o valor por "
            "tonelada, o faturamento dessas viagens também fica errado.",
            typos,
            impact,
        ),
        Finding(
            "weight_unusual",
            Severity.INFO,
            "Peso fora do padrão do caminhão",
            "Carga bem acima ou abaixo do que o mesmo caminhão costuma levar. Pode ser uma "
            "carga parcial, ou a viagem foi lançada na placa errada.",
            unusual,
        ),
    ]


def check_route_rates(scope: _Scope) -> list[Finding]:
    """A rate per tonne far from what the same route (customer, material, origin, destination)
    usually pays."""
    routes: defaultdict[tuple[str, str, str, str], list[Freight]] = defaultdict(list)
    for f in scope.freights:
        if f.gross_rate > 0:
            routes[(f.customer, f.material, f.origin, f.destination)].append(f)

    issues: list[Issue] = []
    impact = 0.0
    for trips in routes.values():
        if len(trips) < MIN_TRIPS_FOR_ROUTE:
            continue
        median = statistics.median(f.gross_rate for f in trips)
        for f in trips:
            if abs(f.gross_rate - median) / median > RATE_DEVIATION:
                issues.append(
                    _trip(
                        f,
                        f"{brl(f.gross_rate)}/t na rota {f.origin} → {f.destination} "
                        f"({f.customer}, {f.material}); o normal é {brl(median)}/t",
                    )
                )
                impact += abs(f.gross_rate - median) * f.weight_t
    return [
        Finding(
            "rate_outlier",
            Severity.WARNING,
            "Valor do frete fora do normal para a rota",
            "O valor por tonelada está muito diferente das outras viagens da mesma rota, cliente "
            "e material. Pode ser erro de digitação ou um preço negociado diferente; vale "
            "conferir com a nota.",
            issues,
            impact,
        )
    ]


def check_freight_math(scope: _Scope) -> list[Finding]:
    """Totals that disagree with weight × rate, or net above gross."""
    issues: list[Issue] = []
    for f in scope.freights:
        expected_gross = f.weight_t * f.gross_rate
        if abs(expected_gross - f.gross_revenue) > MONEY_TOLERANCE:
            issues.append(
                _trip(
                    f,
                    f"Faturamento bruto {brl(f.gross_revenue)}, mas peso × valor dá "
                    f"{brl(expected_gross)}",
                )
            )
        elif f.net_revenue > f.gross_revenue + MONEY_TOLERANCE:
            issues.append(
                _trip(
                    f,
                    f"Produção líquida {brl(f.net_revenue)} maior que o bruto "
                    f"{brl(f.gross_revenue)}",
                )
            )
    return [
        Finding(
            "freight_math",
            Severity.ERROR,
            "Conta do frete não fecha",
            "Os totais da linha não batem com peso × valor por tonelada. Geralmente é uma "
            "fórmula apagada ou um valor digitado por cima dela.",
            issues,
        )
    ]


def check_commissions(scope: _Scope) -> list[Finding]:
    issues: list[Issue] = []
    impact = 0.0
    for f in scope.freights:
        pays = f.commissionable.upper().startswith("S")
        expected = f.net_revenue * f.commission_rate if pays else 0.0
        if abs(expected - f.commission) > MONEY_TOLERANCE:
            reason = f"{number(f.commission_rate * 100)}%" if pays else "não comissiona"
            issues.append(
                _trip(f, f"Comissão {brl(f.commission)}; esperado {brl(expected)} ({reason})")
            )
            impact += abs(expected - f.commission)
    return [
        Finding(
            "commission_mismatch",
            Severity.ERROR,
            "Comissão diferente do esperado",
            "A comissão lançada não corresponde à produção líquida vezes o percentual do "
            "motorista. Isso vai direto para a folha.",
            issues,
            impact,
        )
    ]


def check_missing_net(scope: _Scope) -> list[Finding]:
    """Trips billed gross with no net value: revenue that never reaches net production."""
    missing = [f for f in scope.freights if f.gross_revenue > 0 and f.net_revenue == 0]
    by_route = Counter(f"{f.origin} → {f.destination}" for f in missing)
    routes = ", ".join(f"{route} ({count})" for route, count in by_route.most_common(3))
    gross = sum(f.gross_revenue for f in missing)
    return [
        Finding(
            "missing_net_value",
            Severity.WARNING,
            "Viagens sem valor líquido",
            f"Essas viagens somam {brl(gross)} de faturamento bruto que não entra na produção "
            f"líquida nem na comissão. Principais rotas: {routes}. Se o valor é pago de outra "
            "forma (por exemplo, por viagem na folha), está tudo certo; senão, falta preencher "
            "o valor líquido por tonelada.",
            [
                _trip(f, f"{f.origin} → {f.destination}, bruto {brl(f.gross_revenue)}")
                for f in missing
            ],
            gross,
        )
    ]


def check_missing_fields(scope: _Scope) -> list[Finding]:
    required = {
        "driver": "motorista",
        "plate": "placa",
        "customer": "cliente",
        "material": "material",
    }
    blocking: list[Issue] = []
    no_invoice: list[Issue] = []
    for f in scope.freights:
        empty = [label for name, label in required.items() if not getattr(f, name)]
        if empty:
            blocking.append(_trip(f, "Sem " + ", ".join(empty)))
        elif not f.invoice:
            no_invoice.append(_trip(f, f"{f.customer}, {f.origin} → {f.destination}"))
    return [
        Finding(
            "missing_fields",
            Severity.ERROR,
            "Campos obrigatórios em branco",
            "Viagens sem motorista, placa, cliente ou material ficam de fora dos gráficos e do "
            "fechamento de quem deveria recebê-las.",
            blocking,
        ),
        Finding(
            "missing_invoice",
            Severity.WARNING,
            "Frete sem número de nota fiscal",
            "Sem a NF fica difícil conferir a viagem com o cliente ou provar a entrega.",
            no_invoice,
        ),
    ]


def check_dates(scope: _Scope) -> list[Finding]:
    issues: list[Issue] = []
    for f in scope.freights:
        window = _period_window(f.period)
        if window and not window[0] <= f.date <= window[1]:
            start, end = (d.strftime("%d/%m/%Y") for d in window)
            issues.append(
                _trip(f, f"Lançada na competência {f.period}, que vai de {start} a {end}")
            )
    return [
        Finding(
            "date_outside_period",
            Severity.ERROR,
            "Data fora da competência",
            "A viagem foi lançada numa competência que não inclui a data dela, então entra no "
            "fechamento do mês errado.",
            issues,
        )
    ]


def check_duplicates(scope: _Scope) -> list[Finding]:
    """Identical priced trips. Trips without a net value are left to ``check_missing_net``:
    in practice they are short shuttle runs repeated many times a day on one invoice."""
    groups: defaultdict[tuple[object, ...], list[Freight]] = defaultdict(list)
    for f in scope.freights:
        if f.net_revenue > 0:
            key = (f.date, f.invoice, f.driver, f.plate, f.weight_t, f.origin, f.destination)
            groups[key].append(f)
    issues = [
        _trip(f, f"NF {f.invoice or '—'}, {number(f.weight_t, 2)} t, repetida {len(group)}×")
        for group in groups.values()
        if len(group) > 1
        for f in group[1:]
    ]
    return [
        Finding(
            "possible_duplicate",
            Severity.WARNING,
            "Possível lançamento em duplicidade",
            "Viagens idênticas (mesmo dia, NF, motorista, placa, peso e rota). Se não forem "
            "viagens diferentes de verdade, o faturamento e a comissão estão contados a mais.",
            issues,
            sum(f.gross_revenue for g in groups.values() if len(g) > 1 for f in g[1:]),
        )
    ]


def check_unusual_plate(scope: _Scope) -> list[Finding]:
    plates: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for f in scope.freights:
        plates[f.driver][f.plate] += 1
    issues: list[Issue] = []
    for driver, counts in plates.items():
        usual, usual_trips = counts.most_common(1)[0]
        if usual_trips < MIN_TRIPS_FOR_PROFILE:
            continue
        for plate, trips in counts.items():
            if plate != usual:
                issues.append(
                    Issue(
                        None,
                        None,
                        f"{driver} · {plate}",
                        f"{trips} viagem(ns) na placa {plate}; o normal dele é {usual} "
                        f"({usual_trips} viagens)",
                    )
                )
    return [
        Finding(
            "unusual_plate",
            Severity.INFO,
            "Motorista em caminhão diferente do habitual",
            "Pode ser uma troca de caminhão de verdade ou a placa digitada errada. Afeta o "
            "resultado por caminhão.",
            issues,
        )
    ]


def check_similar_names(scope: _Scope) -> list[Finding]:
    """The same customer, driver or place written two ways splits every total in two."""
    fields = {
        "customer": "Cliente",
        "driver": "Motorista",
        "material": "Material",
        "origin": "Origem",
        "destination": "Destino",
    }
    issues: list[Issue] = []
    for name, label in fields.items():
        counts = Counter(getattr(f, name) for f in scope.freights if getattr(f, name))
        names = sorted(counts)
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                if _probably_same_name(a, b):
                    issues.append(
                        Issue(
                            None,
                            None,
                            label,
                            f'"{a}" ({counts[a]} viagens) e "{b}" ({counts[b]} viagens)',
                        )
                    )
    return [
        Finding(
            "similar_names",
            Severity.WARNING,
            "O mesmo nome escrito de formas diferentes",
            "Nomes quase iguais são tratados como clientes, motoristas ou locais diferentes, e os "
            "totais de cada um aparecem divididos nos gráficos. Se forem o mesmo, padronize "
            "a escrita na planilha.",
            issues,
        )
    ]


#: Words that turn a name into its formal company name ("VALE NORTE" -> "VALE NORTE ENGENHARIA").
COMPANY_SUFFIXES = {
    "ENGENHARIA", "LTDA", "ME", "EPP", "EIRELI", "SA", "S/A", "S.A.", "CONSTRUTORA",
    "CONSTRUCOES", "MINERACAO", "TRANSPORTES", "COMERCIO", "INDUSTRIA", "E", "DO", "DA", "DE",
}  # fmt: skip


def _probably_same_name(a: str, b: str) -> bool:
    pa, pb = _plain(a), _plain(b)
    if pa == pb:  # differ only in accents, case or spacing
        return True
    shorter, longer = sorted((pa, pb), key=len)
    extra = longer.removeprefix(shorter + " ").split() if longer.startswith(shorter + " ") else []
    if extra and len(shorter) >= 4 and all(word in COMPANY_SUFFIXES for word in extra):
        return True
    if [c for c in pa if not c.isdigit()] == [c for c in pb if not c.isdigit()]:
        return False  # "BRITA 0" vs "BRITA 1", "LOTE 3" vs "LOTE 5": different on purpose
    return len(shorter) >= 6 and SequenceMatcher(None, pa, pb).ratio() >= NAME_SIMILARITY


# ─── payroll checks ───────────────────────────────────────────────────────────


def _payroll_issue(p: PayrollSummary, detail: str) -> Issue:
    return Issue(p.ref, None, p.driver, detail)


def check_payroll(scope: _Scope) -> list[Finding]:
    trips: Counter[tuple[str, str]] = Counter()
    commission: defaultdict[tuple[str, str], float] = defaultdict(float)
    for f in scope.freights:
        trips[(f.driver, f.period)] += 1
        commission[(f.driver, f.period)] += f.commission
    adjustments: defaultdict[tuple[str, str], float] = defaultdict(float)
    for a in scope.adjustments:
        adjustments[(a.driver, a.period)] += a.amount

    negative: list[Issue] = []
    mismatches: list[Issue] = []
    for p in scope.payroll:
        key = (p.driver, p.period)
        if p.total_pay < -MONEY_TOLERANCE:
            negative.append(_payroll_issue(p, f"Total a pagar {brl(p.total_pay)}"))
        if p.trips != trips[key]:
            mismatches.append(
                _payroll_issue(
                    p, f"Fechamento diz {p.trips} viagens; os lançamentos têm {trips[key]}"
                )
            )
        if abs(p.commission - commission[key]) > MONEY_TOLERANCE:
            mismatches.append(
                _payroll_issue(
                    p,
                    f"Comissão no fechamento {brl(p.commission)}; nos fretes "
                    f"{brl(commission[key])}",
                )
            )
        if abs(p.total_adjustments - adjustments[key]) > MONEY_TOLERANCE:
            mismatches.append(
                _payroll_issue(
                    p,
                    f"Ajustes no fechamento {brl(p.total_adjustments)}; na aba de ajustes "
                    f"{brl(adjustments[key])}",
                )
            )

    in_payroll = {(p.driver, p.period) for p in scope.payroll}
    missing = [
        Issue(None, None, driver, f"{count} viagens em {period} sem linha no fechamento")
        for (driver, period), count in sorted(trips.items())
        if scope.payroll and (driver, period) not in in_payroll
    ]
    return [
        Finding(
            "payroll_mismatch",
            Severity.ERROR,
            "Fechamento não bate com os lançamentos",
            "O fechamento do motorista não confere com a soma das viagens ou dos ajustes. O "
            "valor pago pode estar errado.",
            mismatches,
        ),
        Finding(
            "payroll_missing_driver",
            Severity.ERROR,
            "Motorista com viagens fora do fechamento",
            "Há viagens no nome de um motorista que não aparece no fechamento: ele pode ficar "
            "sem receber a comissão.",
            missing,
        ),
        Finding(
            "negative_pay",
            Severity.WARNING,
            "Motorista com saldo negativo",
            "Os descontos passaram do que o motorista tem a receber no mês. Pode estar certo "
            "(adiantamento grande), mas vale conferir antes de fechar a folha.",
            negative,
            sum(abs(p.total_pay) for p in scope.payroll if p.total_pay < -MONEY_TOLERANCE),
        ),
    ]


def check_adjustment_signs(scope: _Scope) -> list[Finding]:
    flipped = [
        a
        for a in scope.adjustments
        if (a.kind.upper() in DEDUCTION_KINDS and a.amount > 0)
        or (a.kind.upper() in ADDITION_KINDS and a.amount < 0)
    ]
    issues = [
        Issue(
            a.ref,
            None,
            a.driver,
            f"{a.kind} de {brl(a.amount)}: "
            + ("descontos costumam ser negativos" if a.amount > 0 else "costuma ser positivo"),
        )
        for a in flipped
    ]
    return [
        Finding(
            "adjustment_sign",
            Severity.WARNING,
            "Ajuste de folha com o sinal trocado",
            "Um desconto lançado como crédito (ou o contrário) erra o valor a pagar pelo "
            "dobro do ajuste.",
            issues,
            # Flipping the sign of an amount moves the total by twice that amount.
            2 * sum(abs(a.amount) for a in flipped),
        )
    ]


# ─── costs and fuel ───────────────────────────────────────────────────────────


def check_costs_present(scope: _Scope) -> list[Finding]:
    periods = sorted({f.period for f in scope.freights if f.period}, key=period_sort_key)
    with_fuel = {e.period for e in scope.fuel}
    with_tolls = {e.period for e in scope.tolls}
    issues = []
    for period in periods:
        missing = [
            n
            for n, have in (("combustível", with_fuel), ("pedágio", with_tolls))
            if period not in have
        ]
        if missing:
            issues.append(
                Issue(None, None, period, "Nenhum lançamento de " + " nem de ".join(missing))
            )
    return [
        Finding(
            "costs_missing",
            Severity.WARNING,
            "Mês sem custos de combustível ou pedágio",
            "Sem esses custos, o resultado operacional e a margem do dashboard aparecem "
            "maiores do que são de verdade.",
            issues,
        )
    ]


def check_fuel(scope: _Scope) -> list[Finding]:
    issues: list[Issue] = []
    low, high = KM_PER_LITER_RANGE
    prices = [e.price_per_liter for e in scope.fuel if e.price_per_liter > 0]
    median_price = statistics.median(prices) if len(prices) >= MIN_TRIPS_FOR_ROUTE else 0.0
    for e in scope.fuel:
        who = f"{e.driver} · {e.plate}"
        if e.km_per_liter and not low <= e.km_per_liter <= high:
            issues.append(
                Issue(
                    e.ref,
                    e.date,
                    who,
                    f"{number(e.km_per_liter, 2)} km/L; hodômetro ou litros errados?",
                )
            )
        if (
            median_price
            and abs(e.price_per_liter - median_price) / median_price > FUEL_PRICE_DEVIATION
        ):
            issues.append(
                Issue(
                    e.ref,
                    e.date,
                    who,
                    f"{brl(e.price_per_liter)}/L; a média do mês é {brl(median_price)}/L",
                )
            )
    return [
        Finding(
            "fuel_outlier",
            Severity.WARNING,
            "Abastecimento fora do padrão",
            "Consumo ou preço por litro muito diferentes do normal costumam indicar erro de "
            "digitação do hodômetro ou dos litros, ou um abastecimento que precisa ser conferido.",
            issues,
        )
    ]


CHECKS: tuple[Check, ...] = (
    check_freight_math,
    check_commissions,
    check_dates,
    check_missing_fields,
    check_weights,
    check_route_rates,
    check_duplicates,
    check_similar_names,
    check_missing_net,
    check_unusual_plate,
    check_payroll,
    check_adjustment_signs,
    check_costs_present,
    check_fuel,
)
