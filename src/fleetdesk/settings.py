"""User settings persisted as JSON in the user's application-data folder."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any

THEMES = ("light", "dark", "system")


@dataclass(frozen=True, slots=True)
class Settings:
    #: A workbook path or a folder of workbooks; empty until the user picks one.
    source: str = ""
    theme: str = "dark"
    company_name: str = ""
    #: Local Ollama model for the audit summary; empty picks one automatically.
    ai_model: str = ""


def default_settings_path() -> Path:
    if override := os.environ.get("FLEETDESK_SETTINGS"):
        return Path(override)
    base = os.environ.get("APPDATA")
    root = Path(base) / "FleetDesk" if base else Path.home() / ".fleetdesk"
    return root / "settings.json"


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> Settings:
        try:
            # utf-8-sig: files edited by hand or by PowerShell 5 often start with a BOM.
            raw: Any = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (FileNotFoundError, json.JSONDecodeError):
            return Settings()
        if not isinstance(raw, dict):
            return Settings()
        known = {f.name for f in fields(Settings)}
        settings = Settings(**{k: str(v) for k, v in raw.items() if k in known})
        return settings if settings.theme in THEMES else replace(settings, theme="dark")

    def update(self, **changes: str) -> Settings:
        with self._lock:
            settings = replace(self.load(), **changes)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Write-then-rename so a crash never leaves a half-written settings file.
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), "utf-8")
            os.replace(tmp, self.path)
            return settings
