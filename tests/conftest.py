from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from fleetdesk.app import create_app
from fleetdesk.assistant import (
    NOT_RUNNING,
    AssistantError,
    AssistantStatus,
    LocalAssistant,
    Summary,
)
from fleetdesk.data.audit import AuditReport
from fleetdesk.data.repository import DataRepository
from fleetdesk.dialogs import DialogBusyError, PickKind
from fleetdesk.sample_data import build_workbook
from fleetdesk.settings import SettingsStore
from fleetdesk.updates import RELEASE_API, ZIP_ASSET, UpdateChecker
from fleetdesk.web.services import Services

SAMPLE_TRIPS = 60


@pytest.fixture
def make_workbook(tmp_path: Path) -> Callable[..., Path]:
    def _make(name: str = "fretes.xlsx", month: int = 9, trips: int = SAMPLE_TRIPS) -> Path:
        return build_workbook(tmp_path / name, 2026, month, trips=trips)

    return _make


@pytest.fixture
def sample_workbook(make_workbook: Callable[..., Path]) -> Path:
    return make_workbook()


class FakePicker:
    """Stands in for the native dialog, which cannot be driven from a test."""

    def __init__(self) -> None:
        self.result = ""
        self.busy = False
        self.calls: list[tuple[PickKind, str]] = []

    def __call__(self, kind: PickKind, initial_dir: str) -> str:
        if self.busy:
            raise DialogBusyError
        self.calls.append((kind, initial_dir))
        return self.result


@pytest.fixture
def picker() -> FakePicker:
    return FakePicker()


class FakeAssistant(LocalAssistant):
    """Stands in for Ollama: tests must not depend on a local model being installed."""

    def __init__(self) -> None:
        super().__init__("http://127.0.0.1:9")
        self.available = True
        #: What is missing when not available: NOT_INSTALLED, NOT_RUNNING or NO_MODEL.
        self.state = NOT_RUNNING
        self.failure: str | None = None
        self.prompts: list[AuditReport] = []

    def status(self, preferred_model: str = "") -> AssistantStatus:
        if not self.available:
            return AssistantStatus(
                available=False, message="O Ollama não está aberto.", state=self.state
            )
        models = ["qwen2.5:3b", "qwen2.5:7b"]
        return AssistantStatus(True, preferred_model or models[0], models)

    def summarize(self, report: AuditReport, model: str) -> Summary:
        if self.failure:
            raise AssistantError(self.failure)
        self.prompts.append(report)
        return Summary(f"Resumo de {len(report.findings)} achados.", model, 0.1)


@pytest.fixture
def assistant() -> FakeAssistant:
    return FakeAssistant()


class FakeReleases:
    """Serves a fake GitHub "latest release" and its assets instead of the network."""

    def __init__(self) -> None:
        self.responses: dict[str, bytes] = {}
        self.offline = True

    def publish(self, version: str, archive: bytes) -> None:
        import hashlib
        import json

        base = f"https://example.test/v{version}"
        self.responses = {
            RELEASE_API: json.dumps(
                {
                    "tag_name": f"v{version}",
                    "html_url": base,
                    "assets": [
                        {"name": ZIP_ASSET, "browser_download_url": f"{base}/{ZIP_ASSET}"},
                        {
                            "name": f"{ZIP_ASSET}.sha256",
                            "browser_download_url": f"{base}/{ZIP_ASSET}.sha256",
                        },
                    ],
                }
            ).encode(),
            f"{base}/{ZIP_ASSET}": archive,
            f"{base}/{ZIP_ASSET}.sha256": f"{hashlib.sha256(archive).hexdigest()}  x".encode(),
        }
        self.offline = False

    def __call__(self, url: str, timeout: float) -> bytes:
        if self.offline or url not in self.responses:
            raise OSError("offline")
        return self.responses[url]


@pytest.fixture
def releases() -> FakeReleases:
    return FakeReleases()


@pytest.fixture
def updates(releases: FakeReleases) -> UpdateChecker:
    return UpdateChecker(current_version="0.1.0", fetch=releases, runtime=None)


class ShutdownSpy:
    """Records shutdown requests instead of killing the test process."""

    def __init__(self) -> None:
        self.calls = 0

    def append_call(self) -> None:
        self.calls += 1


@pytest.fixture
def shutdown_calls() -> ShutdownSpy:
    return ShutdownSpy()


@pytest.fixture
def settings_store(tmp_path: Path) -> SettingsStore:
    return SettingsStore(tmp_path / "config" / "settings.json")


@pytest.fixture
def app(
    settings_store: SettingsStore,
    picker: FakePicker,
    shutdown_calls: ShutdownSpy,
    assistant: FakeAssistant,
    updates: UpdateChecker,
) -> Flask:
    app = create_app(
        Services(
            settings=settings_store,
            repository=DataRepository(),
            pick_path=picker,
            shutdown=shutdown_calls.append_call,
            assistant=assistant,
            updates=updates,
        )
    )
    app.config.update(TESTING=True)
    app.config["ALLOWED_HOSTS"].add("localhost")  # the Flask test client's default host
    return app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def configured_client(
    client: FlaskClient, settings_store: SettingsStore, sample_workbook: Path
) -> FlaskClient:
    settings_store.update(source=str(sample_workbook))
    return client
