"""Application services shared by the views, stored on the Flask app."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from flask import Flask, current_app

from fleetdesk.assistant import LocalAssistant
from fleetdesk.data.repository import DataRepository
from fleetdesk.dialogs import PickKind
from fleetdesk.settings import SettingsStore

_EXTENSION_KEY = "fleetdesk"


@dataclass(frozen=True, slots=True)
class Services:
    settings: SettingsStore
    repository: DataRepository
    #: Opens a native picker; swapped out in tests.
    pick_path: Callable[[PickKind, str], str]
    #: Stops the whole process shortly after the current response is sent.
    shutdown: Callable[[], None]
    #: Local LLM used for the optional audit summary.
    assistant: LocalAssistant

    def install(self, app: Flask) -> None:
        app.extensions[_EXTENSION_KEY] = self


def services() -> Services:
    return cast(Services, current_app.extensions[_EXTENSION_KEY])
