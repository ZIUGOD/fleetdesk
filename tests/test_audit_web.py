from __future__ import annotations

from pathlib import Path

import pytest
from flask.testing import FlaskClient

from fleetdesk.assistant import LocalAssistant, build_prompt, overview, where
from fleetdesk.data.audit import run_audit
from fleetdesk.data.repository import DataRepository
from fleetdesk.sample_data import build_workbook
from fleetdesk.settings import SettingsStore
from tests.conftest import FakeAssistant


@pytest.fixture
def faulty_client(
    client: FlaskClient, settings_store: SettingsStore, tmp_path: Path
) -> FlaskClient:
    workbook = build_workbook(tmp_path / "faulty.xlsx", 2026, 9, trips=200, mistakes=True)
    settings_store.update(source=str(workbook))
    return client


def test_audit_page_lists_findings_with_rows(faulty_client: FlaskClient) -> None:
    html = faulty_client.get("/audit").get_data(as_text=True)

    assert "Peso provavelmente digitado errado" in html
    assert "aba LANÇAMENTOS" in html
    assert "Gerar resumo" in html


def test_sidebar_badge_counts_findings_to_check(faulty_client: FlaskClient) -> None:
    html = faulty_client.get("/dashboard").get_data(as_text=True)
    assert 'class="nav-badge"' in html


def test_summary_comes_from_the_local_assistant(
    faulty_client: FlaskClient, assistant: FakeAssistant
) -> None:
    result = faulty_client.post("/audit/summary", data={"period": "SET/2026"}).get_json()

    assert result["text"].startswith("Resumo de")
    assert result["model"] == "qwen2.5:3b"
    assert assistant.prompts[0].period == "SET/2026"


def test_summary_explains_when_ollama_is_off(
    faulty_client: FlaskClient, assistant: FakeAssistant
) -> None:
    assistant.available = False

    response = faulty_client.post("/audit/summary")
    assert response.status_code == 503
    assert "Ollama" in response.get_json()["error"]
    assert "Ollama" in faulty_client.get("/audit").get_data(as_text=True)


def test_summary_reports_model_failures(
    faulty_client: FlaskClient, assistant: FakeAssistant
) -> None:
    assistant.failure = "A IA demorou demais para responder."

    response = faulty_client.post("/audit/summary")
    assert response.status_code == 502
    assert response.get_json()["error"] == assistant.failure


def test_chosen_model_is_saved(faulty_client: FlaskClient, settings_store: SettingsStore) -> None:
    faulty_client.post("/settings", data={"ai_model": "qwen2.5:7b"})
    assert settings_store.load().ai_model == "qwen2.5:7b"


def test_unreachable_ollama_is_reported_not_raised() -> None:
    status = LocalAssistant("http://127.0.0.1:9").status()
    assert not status.available
    assert "Ollama" in status.message


def test_prompt_is_prioritised_and_preformatted(tmp_path: Path) -> None:
    workbook = build_workbook(tmp_path / "faulty.xlsx", 2026, 9, trips=200, mistakes=True)
    report = run_audit(DataRepository().load(str(workbook)))

    prompt = build_prompt(report)

    assert '"numero": 1' in prompt
    assert '"problema": "Peso provavelmente digitado errado"' in prompt  # errors come first
    assert "aba LANÇAMENTOS, linha" in prompt
    assert "R$ " in prompt


def test_overview_counts_are_computed_not_left_to_the_model(tmp_path: Path) -> None:
    clean = build_workbook(tmp_path / "a" / "clean.xlsx", 2026, 9, trips=120)
    faulty = build_workbook(tmp_path / "b" / "faulty.xlsx", 2026, 9, trips=200, mistakes=True)

    clean_text = overview(run_audit(DataRepository().load(str(clean)), "SET/2026"))
    faulty_text = overview(run_audit(DataRepository().load(str(faulty))))

    assert clean_text.endswith("na competência SET/2026 e não achei problemas.")
    assert "1 tipo de erro provável e 3 pontos para conferir" in faulty_text
    assert '"visao_geral"' in build_prompt(run_audit(DataRepository().load(str(faulty))))


def test_where_summarises_rows() -> None:
    from fleetdesk.data.audit import Issue
    from fleetdesk.data.models import SourceRef

    issues = [Issue(SourceRef("f.xlsx", "LANÇAMENTOS", n), None, "", "") for n in range(1, 8)]
    assert where(issues) == "aba LANÇAMENTOS, linhas 1, 2, 3, 4 e mais 3"
