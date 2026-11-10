"""Page views. Endpoint names and query parameters are English; UI text is pt-BR."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import asdict, dataclass

from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.wrappers import Response

from fleetdesk import __version__
from fleetdesk.assistant import AssistantError
from fleetdesk.data import analytics
from fleetdesk.data.audit import AuditReport, run_audit
from fleetdesk.data.models import Dataset, Freight, empty_dataset
from fleetdesk.data.repository import WORKBOOK_EXTENSIONS, list_workbooks
from fleetdesk.dialogs import DialogBusyError, PickKind
from fleetdesk.settings import THEMES
from fleetdesk.updates import DOWNLOAD_PAGE, UpdateError
from fleetdesk.web.services import services

log = logging.getLogger(__name__)
bp = Blueprint("pages", __name__)

PAGE_SIZE = 100
#: Occurrences listed per finding; the rest are summarised as a count.
AUDIT_ISSUE_LIMIT = 200


def load_dataset() -> Dataset | None:
    """The current dataset, or None when no usable source is configured.

    When there is none, ``g.data_problem`` says why in pt-BR, for the banner every page shows.
    """
    source = services().settings.load().source
    if not source:
        g.data_problem = "Nenhuma planilha escolhida ainda."
        return None
    if not os.path.exists(source):
        g.data_problem = (
            f"A planilha ou pasta escolhida não foi encontrada: {source}. Ela pode ter sido "
            "movida, renomeada, ou o Google Drive pode estar desconectado."
        )
        return None
    try:
        dataset = services().repository.load(source)
    except Exception:  # any failure must still leave every page usable
        log.exception("Could not load data source %s", source)
        g.data_problem = (
            "Não foi possível ler as planilhas. Se alguém estiver salvando ou o Google Drive "
            "estiver sincronizando, espere um pouco e clique em Recarregar."
        )
        return None
    g.dataset = dataset
    return dataset


def dataset_or_empty() -> Dataset:
    """The current dataset, or an empty one so a page still opens (with the banner)."""
    return load_dataset() or empty_dataset()


@dataclass(frozen=True, slots=True)
class FreightFilters:
    period: str = ""
    driver: str = ""
    customer: str = ""
    material: str = ""

    @classmethod
    def from_request(cls) -> FreightFilters:
        return cls(**{name: request.args.get(name, "") for name in cls.__dataclass_fields__})

    def apply(self, freights: list[Freight]) -> list[Freight]:
        selected = analytics.in_period(freights, self.period)
        for name in ("driver", "customer", "material"):
            if wanted := getattr(self, name):
                selected = [f for f in selected if getattr(f, name) == wanted]
        return selected


def _filter_options(dataset: Dataset) -> dict[str, list[str]]:
    return {
        "periods": dataset.periods,
        "drivers": dataset.drivers,
        "customers": dataset.customers,
        "materials": dataset.materials,
    }


@bp.get("/")
def index() -> Response:
    # First run: straight to choosing the workbooks.
    first_run = not services().settings.load().source
    return redirect(url_for("pages.settings" if first_run else "pages.dashboard"))


@bp.get("/dashboard")
def dashboard() -> str | Response:
    dataset = dataset_or_empty()

    filters = FreightFilters.from_request()
    freights = filters.apply(dataset.freights)
    charts: dict[str, analytics.Series | analytics.DailySeries] = {
        "daily": analytics.daily_series(freights),
        "by_driver": analytics.totals_by(freights, "driver", "net_revenue"),
        "by_customer": analytics.totals_by(
            freights, "customer", "gross_revenue", limit=15, fold_rest=True
        ),
        "by_material": analytics.totals_by(
            freights, "material", "weight_t", limit=12, fold_rest=True
        ),
        "by_origin": analytics.totals_by(freights, "origin", "weight_t", limit=12, fold_rest=True),
    }
    kpis = analytics.compute_kpis(
        freights,
        analytics.in_period(dataset.payroll, filters.period),
        analytics.in_period(dataset.fuel, filters.period),
        analytics.in_period(dataset.tolls, filters.period),
    )
    return render_template(
        "dashboard.html",
        kpis=kpis,
        charts={name: asdict(series) for name, series in charts.items()},
        filters=filters,
        **_filter_options(dataset),
    )


@bp.get("/freights")
def freights() -> str | Response:
    dataset = dataset_or_empty()

    filters = FreightFilters.from_request()
    rows = filters.apply(dataset.freights)
    page_count = max(1, -(-len(rows) // PAGE_SIZE))
    try:
        page = min(max(1, int(request.args.get("page", 1))), page_count)
    except ValueError:
        page = 1
    start = (page - 1) * PAGE_SIZE
    return render_template(
        "freights.html",
        rows=rows[start : start + PAGE_SIZE],
        page=page,
        page_count=page_count,
        total_rows=len(rows),
        total_weight=sum(f.weight_t for f in rows),
        total_gross=sum(f.gross_revenue for f in rows),
        total_net=sum(f.net_revenue for f in rows),
        filters=filters,
        **_filter_options(dataset),
    )


@bp.get("/payroll")
def payroll() -> str | Response:
    dataset = dataset_or_empty()

    period = request.args.get("period", "")
    driver = request.args.get("driver", "")
    rows = analytics.in_period(dataset.payroll, period)
    if driver:
        rows = [r for r in rows if r.driver == driver]

    return render_template(
        "payroll.html",
        rows=rows,
        periods=dataset.periods,
        drivers=sorted({r.driver for r in dataset.payroll if r.driver}),
        selected_period=period,
        selected_driver=driver,
        show_period_column=not period and len({r.period for r in rows}) > 1,
        totals={
            field: sum(getattr(r, field) for r in rows)
            for field in (
                "trips",
                "tonnes",
                "gross_revenue",
                "net_revenue",
                "commission",
                "total_adjustments",
                "total_pay",
            )
        },
    )


@bp.get("/payroll/adjustments")
def adjustments() -> str | Response:
    dataset = dataset_or_empty()

    period = request.args.get("period", "")
    driver = request.args.get("driver", "")
    rows = analytics.in_period(dataset.adjustments, period)
    statements = analytics.driver_statements(
        analytics.in_period(dataset.freights, period),
        rows,
        analytics.in_period(dataset.fuel, period),
        analytics.in_period(dataset.tolls, period),
    )
    if driver:
        rows = [r for r in rows if r.driver == driver]
        statements = [s for s in statements if s.driver == driver]

    return render_template(
        "adjustments.html",
        rows=rows,
        statements=statements,
        show_costs=any(s.trip_costs for s in statements),
        periods=dataset.periods,
        drivers=sorted({r.driver for r in dataset.adjustments if r.driver} | set(dataset.drivers)),
        selected_period=period,
        selected_driver=driver,
        total_gross=sum(s.gross_revenue for s in statements),
        total_net=sum(s.net_revenue for s in statements),
        total_commission=sum(s.commission for s in statements),
        total_costs=sum(s.trip_costs for s in statements),
        total_deductions=sum(s.deductions for s in statements),
        total_additions=sum(s.additions for s in statements),
    )


@bp.get("/fuel")
def fuel() -> str | Response:
    dataset = dataset_or_empty()

    period = request.args.get("period", "")
    driver = request.args.get("driver", "")
    rows = analytics.in_period(dataset.fuel, period)
    if driver:
        rows = [r for r in rows if r.driver == driver]

    return render_template(
        "fuel.html",
        rows=rows,
        periods=dataset.periods,
        drivers=dataset.drivers,
        selected_period=period,
        selected_driver=driver,
        total_spent=sum(r.total for r in rows),
        total_liters=sum(r.liters for r in rows),
    )


def _validate_source(raw: str) -> tuple[str, str | None]:
    """Normalise a typed path and return it with a pt-BR error message, if invalid."""
    cleaned = raw.strip().strip('"')
    path = os.path.normpath(cleaned) if cleaned else ""
    if not path or not os.path.exists(path):
        return path, f"Arquivo ou pasta não encontrado: {path or '(vazio)'}"
    if os.path.isfile(path) and not path.lower().endswith(WORKBOOK_EXTENSIONS):
        return path, "O arquivo precisa ser uma planilha do Excel (.xlsx)."
    if os.path.isdir(path) and not list_workbooks(path):
        return path, f"Nenhuma planilha .xlsx encontrada na pasta: {path}"
    return path, None


@bp.route("/settings", methods=["GET", "POST"])
def settings() -> str | Response:
    store = services().settings
    error = None
    if request.method == "POST":
        form = request.form
        if "theme" in form:
            if form["theme"] in THEMES:
                store.update(theme=form["theme"])
            return redirect(url_for("pages.settings"))
        if "company_name" in form:
            store.update(company_name=form["company_name"].strip()[:60])
            return redirect(url_for("pages.settings", saved="company"))
        if "check_updates" in form:
            store.update(check_updates=form["check_updates"] == "1")
            return redirect(url_for("pages.settings") + "#updates")
        if "ai_model" in form:
            store.update(ai_model=form["ai_model"].strip()[:80])
            return redirect(url_for("pages.settings", saved="ai") + "#ai")
        path, error = _validate_source(form.get("source", ""))
        if error is None:
            store.update(source=path)
            services().repository.invalidate()
            return redirect(url_for("pages.settings", saved="source"))

    dataset = load_dataset()
    return render_template(
        "settings.html",
        source=store.load().source,
        files=dataset.files if dataset else [],
        saved=request.args.get("saved"),
        error=error,
        ai_model=store.load().ai_model,
        assistant=services().assistant.status(store.load().ai_model),
        check_updates=store.load().check_updates,
        checked_update=services().updates.cached(),
    )


@bp.post("/settings/pick/<kind>")
def pick_source(kind: str) -> Response | tuple[Response, int]:
    if kind not in ("file", "folder"):
        abort(404)
    current = services().settings.load().source
    initial = current if os.path.isdir(current) else os.path.dirname(current)
    if not os.path.isdir(initial):
        initial = os.path.expanduser("~")
    picked_kind: PickKind = "file" if kind == "file" else "folder"
    try:
        path = services().pick_path(picked_kind, initial)
    except DialogBusyError:
        return jsonify(error="Já existe uma janela de seleção aberta."), 409
    return jsonify(path=path)


def audit_for(dataset: Dataset, period: str = "") -> AuditReport:
    """Audit of the dataset, recomputed only when the data (or the period) changes.

    The repository hands back the same Dataset object until a workbook changes, so object
    identity is a reliable cache key; the sidebar badge reads this on every page.
    """
    cache: dict[str, tuple[Dataset, AuditReport]] = current_app.extensions.setdefault(
        "fleetdesk.audits", {}
    )
    cached = cache.get(period)
    if cached and cached[0] is dataset:
        return cached[1]
    report = run_audit(dataset, period)
    cache[period] = (dataset, report)
    return report


@bp.get("/audit")
def audit() -> str | Response:
    dataset = dataset_or_empty()
    period = request.args.get("period", "")
    try:
        report = audit_for(dataset, period)
        audit_failed = False
    except Exception:
        log.exception("Audit failed")
        report, audit_failed = AuditReport(period, [], 0), True
    return render_template(
        "audit.html",
        report=report,
        audit_failed=audit_failed,
        periods=dataset.periods,
        selected_period=period,
        assistant=services().assistant.status(services().settings.load().ai_model),
        issue_limit=AUDIT_ISSUE_LIMIT,
    )


@bp.post("/audit/summary")
def audit_summary() -> Response | tuple[Response, int]:
    dataset = load_dataset()
    if dataset is None:
        return jsonify(error="Nenhuma planilha carregada."), 409
    status = services().assistant.status(services().settings.load().ai_model)
    if not status.available:
        return jsonify(error=status.message), 503
    report = audit_for(dataset, request.form.get("period", ""))
    try:
        summary = services().assistant.summarize(report, status.model)
    except AssistantError as exc:
        log.warning("AI summary failed: %s", exc)
        return jsonify(error=str(exc)), 502
    return jsonify(text=summary.text, model=summary.model, seconds=round(summary.seconds, 1))


@bp.get("/version")
def version() -> Response:
    return jsonify(version=__version__)


@bp.post("/update/check")
def check_for_update() -> Response:
    services().updates.available(force=True)
    return redirect(url_for("pages.settings", saved="update-check") + "#updates")


@bp.post("/update")
def update_app() -> Response | tuple[Response, int]:
    updates = services().updates
    release = updates.available()
    if release is None:
        return jsonify(error="Você já está na versão mais recente."), 409
    if not updates.can_self_update:
        return jsonify(error="Baixe a versão nova na página de download.", url=DOWNLOAD_PAGE), 409
    try:
        staged = updates.prepare(release)
    except UpdateError as exc:
        log.warning("Update to %s failed: %s", release.version, exc)
        return jsonify(error=str(exc)), 502
    host, port = current_app.config["SERVER_ADDRESS"]
    # After the response: swapping the code out from under a request in flight would break it.
    threading.Timer(0.5, updates.finish, args=(staged, host, port, services().shutdown)).start()
    log.info("Updating to %s; restarting", release.version)
    return jsonify(version=release.version)


@bp.post("/quit")
def quit_app() -> str:
    services().shutdown()
    return render_template("stopped.html")


@bp.get("/reload")
def reload() -> Response:
    services().repository.invalidate()
    back = request.referrer or ""
    return redirect(back if back.startswith(request.host_url) else url_for("pages.dashboard"))
