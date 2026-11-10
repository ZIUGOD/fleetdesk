from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from flask.testing import FlaskClient

from fleetdesk.settings import SettingsStore
from tests.conftest import FakePicker, ShutdownSpy

PAGES = ["/dashboard", "/freights", "/payroll", "/payroll/adjustments", "/fuel", "/settings"]


TABS = ["/dashboard", "/audit", "/freights", "/payroll", "/payroll/adjustments", "/fuel"]


def test_first_run_opens_settings(client: FlaskClient) -> None:
    response = client.get("/")
    assert response.headers["Location"].endswith("/settings")
    assert "Para começar" in client.get("/settings").get_data(as_text=True)


@pytest.mark.parametrize("url", TABS)
def test_every_tab_opens_without_a_source(client: FlaskClient, url: str) -> None:
    response = client.get(url)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Sem dados para mostrar" in html
    assert "Nenhuma planilha escolhida ainda." in html


@pytest.mark.parametrize("url", TABS)
def test_every_tab_opens_when_the_source_is_gone(
    client: FlaskClient, settings_store: SettingsStore, tmp_path: Path, url: str
) -> None:
    settings_store.update(source=str(tmp_path / "moved.xlsx"))
    response = client.get(url)
    assert response.status_code == 200
    assert "não foi encontrada" in response.get_data(as_text=True)


@pytest.mark.parametrize("url", TABS)
def test_every_tab_opens_when_reading_fails(
    configured_client: FlaskClient, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    def broken(*args: object) -> None:
        raise ValueError("unexpected workbook layout")

    monkeypatch.setattr("fleetdesk.data.repository.DataRepository.load", broken)
    response = configured_client.get(url)
    assert response.status_code == 200
    assert "Não foi possível ler as planilhas" in response.get_data(as_text=True)


def test_an_unexpected_error_keeps_the_menu(
    configured_client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise ZeroDivisionError

    monkeypatch.setattr("fleetdesk.data.analytics.compute_kpis", broken)
    response = configured_client.get("/dashboard")
    assert response.status_code == 500
    html = response.get_data(as_text=True)
    assert "Algo deu errado nesta tela" in html
    assert 'href="/fuel"' in html  # the sidebar is still there


def test_kpis_explain_how_they_are_calculated(configured_client: FlaskClient) -> None:
    html = configured_client.get("/dashboard").get_data(as_text=True)
    assert html.count('class="info-tip"') == 8
    assert "Produção líquida − comissões − combustível − pedágio" in html


@pytest.mark.parametrize("url", PAGES)
def test_every_page_renders_with_sample_data(configured_client: FlaskClient, url: str) -> None:
    assert configured_client.get(url).status_code == 200


def test_dashboard_filters_by_driver(configured_client: FlaskClient) -> None:
    html = configured_client.get("/dashboard?driver=ANDRÉ").get_data(as_text=True)
    assert "· ANDRÉ" in html


def test_adjustments_page_shows_each_drivers_revenue(configured_client: FlaskClient) -> None:
    html = configured_client.get("/payroll/adjustments").get_data(as_text=True)
    assert "Faturamento e ajustes por motorista" in html
    assert "Fat. bruto" in html

    one = configured_client.get("/payroll/adjustments?driver=ANDRÉ").get_data(as_text=True)
    assert one.count('href="/payroll/adjustments?driver=') == 1  # only ANDRÉ's row


def test_freights_tolerates_a_bad_page_number(configured_client: FlaskClient) -> None:
    assert configured_client.get("/freights?page=abc").status_code == 200
    assert configured_client.get("/freights?page=9999").status_code == 200


def test_switching_source_updates_the_dashboard(
    client: FlaskClient, tmp_path: Path, make_workbook: Callable[..., Path]
) -> None:
    small = make_workbook("a/small.xlsx", trips=10)
    make_workbook("b/big.xlsx", trips=25)

    client.post("/settings", data={"source": str(small)})
    assert "10 viagens" in client.get("/dashboard").get_data(as_text=True)

    client.post("/settings", data={"source": str(tmp_path / "b")})
    assert "25 viagens" in client.get("/dashboard").get_data(as_text=True)


def test_pages_are_never_served_from_the_browser_cache(configured_client: FlaskClient) -> None:
    response = configured_client.get("/dashboard")
    assert "no-store" in response.headers["Cache-Control"]
    static = configured_client.get("/static/css/app.css")
    assert "no-store" not in static.headers.get("Cache-Control", "")


def test_saving_a_typed_source(
    client: FlaskClient, settings_store: SettingsStore, sample_workbook: Path
) -> None:
    response = client.post("/settings", data={"source": f'"{sample_workbook}"'})

    assert response.status_code == 302
    assert settings_store.load().source == str(sample_workbook)


@pytest.mark.parametrize(
    ("typed", "message"),
    [("C:/does/not/exist.xlsx", "não encontrado"), ("", "(vazio)")],
)
def test_invalid_sources_are_rejected(
    client: FlaskClient, settings_store: SettingsStore, typed: str, message: str
) -> None:
    html = client.post("/settings", data={"source": typed}).get_data(as_text=True)

    assert message in html
    assert settings_store.load().source == ""


def test_non_workbook_file_is_rejected(client: FlaskClient, tmp_path: Path) -> None:
    text_file = tmp_path / "notes.txt"
    text_file.write_text("x")
    html = client.post("/settings", data={"source": str(text_file)}).get_data(as_text=True)
    assert "planilha do Excel" in html


def test_theme_and_company_name_are_saved(
    client: FlaskClient, settings_store: SettingsStore
) -> None:
    client.post("/settings", data={"theme": "light"})
    client.post("/settings", data={"theme": "pink"})
    client.post("/settings", data={"company_name": "  Transportadora Exemplo  "})

    settings = settings_store.load()
    assert settings.theme == "light"
    assert settings.company_name == "Transportadora Exemplo"
    assert "Transportadora Exemplo" in client.get("/settings").get_data(as_text=True)


def test_picker_returns_the_chosen_path(client: FlaskClient, picker: FakePicker) -> None:
    picker.result = r"C:\data\fretes.xlsx"

    response = client.post("/settings/pick/file")

    assert response.get_json() == {"path": r"C:\data\fretes.xlsx"}
    assert picker.calls[0][0] == "file"
    assert client.post("/settings/pick/everything").status_code == 404


def test_picker_reports_when_a_dialog_is_already_open(
    client: FlaskClient, picker: FakePicker
) -> None:
    picker.busy = True
    assert client.post("/settings/pick/folder").status_code == 409


def test_quit_stops_the_app_and_says_so(client: FlaskClient, shutdown_calls: ShutdownSpy) -> None:
    assert client.get("/quit").status_code == 405  # never on a plain link or prefetch
    response = client.post("/quit")

    assert shutdown_calls.calls == 1
    assert "foi encerrado" in response.get_data(as_text=True)


def test_quit_from_another_site_is_refused(
    client: FlaskClient, shutdown_calls: ShutdownSpy
) -> None:
    response = client.post("/quit", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert shutdown_calls.calls == 0


def test_requests_from_other_sites_are_refused(
    client: FlaskClient, settings_store: SettingsStore
) -> None:
    response = client.post(
        "/settings", data={"theme": "light"}, headers={"Origin": "https://evil.example"}
    )

    assert response.status_code == 403
    assert settings_store.load().theme == "dark"


def test_unknown_host_header_is_refused(client: FlaskClient) -> None:
    assert client.get("/settings", headers={"Host": "evil.example:5000"}).status_code == 403


def test_reload_never_redirects_off_site(configured_client: FlaskClient) -> None:
    response = configured_client.get("/reload", headers={"Referer": "https://evil.example/"})
    assert response.headers["Location"].endswith("/dashboard")
