"""Check for new releases and update the bundled app in place.

The update deliberately never runs a downloaded executable: on PCs with Smart App Control an
unsigned installer is blocked outright. Instead it replaces only the pure-Python
``Lib/site-packages`` of the bundled runtime (FleetDesk and its dependencies), then restarts
through the already-installed, PSF-signed ``pythonw.exe``. A release that changes the Python
runtime itself cannot be applied this way and asks the user to reinstall.

The only network access is to GitHub's public release API and download URLs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fleetdesk import __version__

RELEASE_API = os.environ.get(
    "FLEETDESK_RELEASE_API", "https://api.github.com/repos/ZIUGOD/fleetdesk/releases/latest"
)
DOWNLOAD_PAGE = "https://ziugod.github.io/fleetdesk/"
ZIP_ASSET = "FleetDesk-windows.zip"
#: Re-check at most this often while the app keeps running.
CHECK_INTERVAL_S = 6 * 3600
USER_AGENT = f"FleetDesk/{__version__} (update check)"

SITE_PACKAGES = Path("Lib") / "site-packages"
_BUNDLE_PREFIX = "FleetDesk/runtime/"


class UpdateError(RuntimeError):
    """The update could not be applied (message is pt-BR, shown to the user)."""


@dataclass(frozen=True, slots=True)
class Release:
    version: str
    url: str
    zip_url: str
    sha256_url: str | None


def parse_version(text: str) -> tuple[int, ...]:
    """'v0.10.2' -> (0, 10, 2); anything unparsable sorts below every real version."""
    numbers = re.findall(r"\d+", text.split("-")[0])
    return tuple(int(n) for n in numbers[:3]) if numbers else (0,)


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def bundled_runtime() -> Path | None:
    """The bundled Python runtime folder, or None when running from a dev checkout."""
    runtime = Path(sys.base_prefix)
    return runtime if any(runtime.glob("python3*._pth")) else None


def _get(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data: bytes = response.read()
        return data


class UpdateChecker:
    def __init__(
        self,
        current_version: str = __version__,
        fetch: Callable[[str, float], bytes] = _get,
        runtime: Path | None = None,
    ) -> None:
        self.current_version = current_version
        self._fetch = fetch
        self.runtime = runtime if runtime is not None else bundled_runtime()
        self._lock = threading.Lock()
        self._checked_at: float | None = None
        self._latest: Release | None = None

    @property
    def can_self_update(self) -> bool:
        return self.runtime is not None

    def available(self, force: bool = False) -> Release | None:
        """The newest release if it is newer than this version. Never raises."""
        with self._lock:
            # monotonic() counts from boot, so "never checked" must not be stored as 0.
            stale = (
                self._checked_at is None or time.monotonic() - self._checked_at > CHECK_INTERVAL_S
            )
            if force or stale:
                self._latest = self._fetch_latest()
                self._checked_at = time.monotonic()
            latest = self._latest
        return latest if latest and is_newer(latest.version, self.current_version) else None

    def cached(self) -> Release | None:
        """What the last check found, without touching the network (for every page)."""
        latest = self._latest
        return latest if latest and is_newer(latest.version, self.current_version) else None

    def _fetch_latest(self) -> Release | None:
        try:
            data: dict[str, Any] = json.loads(self._fetch(RELEASE_API, 5))
        except Exception:  # offline, rate-limited, or GitHub down: simply no update shown
            return None
        assets = {a.get("name"): a.get("browser_download_url") for a in data.get("assets", [])}
        if ZIP_ASSET not in assets or not data.get("tag_name"):
            return None
        return Release(
            version=str(data["tag_name"]).lstrip("v"),
            url=str(data.get("html_url") or DOWNLOAD_PAGE),
            zip_url=str(assets[ZIP_ASSET]),
            sha256_url=assets.get(f"{ZIP_ASSET}.sha256"),
        )

    def prepare(self, release: Release) -> Path:
        """Download and verify the release and stage its site-packages next to the current one.

        Returns the staged folder; ``activate`` swaps it in. Raises UpdateError.
        """
        if self.runtime is None:
            raise UpdateError("Esta cópia não pode se atualizar sozinha. Baixe a versão nova.")
        try:
            archive = self._fetch(release.zip_url, 120)
            expected = (
                self._fetch(release.sha256_url, 15).decode().split()[0].lower()
                if release.sha256_url
                else None
            )
        except Exception as exc:
            raise UpdateError(f"Não foi possível baixar a atualização: {exc}") from exc
        if expected is None:
            raise UpdateError("A versão nova não tem código de verificação (SHA-256).")
        if hashlib.sha256(archive).hexdigest() != expected:
            raise UpdateError("O arquivo baixado está corrompido (SHA-256 não confere).")

        staged = self.runtime / SITE_PACKAGES.with_name("site-packages.new")
        shutil.rmtree(staged, ignore_errors=True)
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / ZIP_ASSET
            zip_path.write_bytes(archive)
            with zipfile.ZipFile(zip_path) as bundle:
                names = bundle.namelist()
                if not self._same_python(names):
                    raise UpdateError(
                        "Esta versão troca o Python interno do FleetDesk e precisa ser "
                        "instalada de novo pela página de download."
                    )
                prefix = _BUNDLE_PREFIX + SITE_PACKAGES.as_posix() + "/"
                for name in names:
                    if not name.startswith(prefix) or name.endswith("/"):
                        continue
                    relative = Path(name[len(prefix) :])
                    if ".." in relative.parts or relative.is_absolute():
                        raise UpdateError("O pacote da atualização tem um caminho inválido.")
                    target = staged / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(bundle.read(name))
        if not (staged / "fleetdesk" / "__init__.py").is_file():
            shutil.rmtree(staged, ignore_errors=True)
            raise UpdateError("O pacote da atualização está incompleto.")
        return staged

    def _same_python(self, names: list[str]) -> bool:
        assert self.runtime is not None
        mine = sorted(p.name for p in self.runtime.glob("python3*.dll"))
        theirs = sorted(
            n[len(_BUNDLE_PREFIX) :]
            for n in names
            if re.fullmatch(re.escape(_BUNDLE_PREFIX) + r"python3\d*\.dll", n)
        )
        return bool(mine) and mine == theirs

    def activate(self, staged: Path) -> None:
        """Swap the staged site-packages in, keeping the old one until the next start."""
        assert self.runtime is not None
        current = self.runtime / SITE_PACKAGES
        previous = current.with_name("site-packages.old")
        shutil.rmtree(previous, ignore_errors=True)
        current.rename(previous)
        try:
            staged.rename(current)
        except OSError:
            previous.rename(current)  # put the working version back
            raise

    def finish(self, staged: Path, host: str, port: int, shutdown: Callable[[], None]) -> None:
        """Swap the new code in, schedule the restart and stop this process."""
        self.activate(staged)
        self.relaunch_when_stopped(host, port)
        shutdown()

    def cleanup(self) -> None:
        """Remove what the last update left behind (safe to call on every start)."""
        if self.runtime is not None:
            for leftover in ("site-packages.old", "site-packages.new"):
                shutil.rmtree(self.runtime / "Lib" / leftover, ignore_errors=True)

    def relaunch_when_stopped(self, host: str, port: int) -> None:
        """Start a detached, signed pythonw that reopens FleetDesk once this one has exited."""
        assert self.runtime is not None
        waiter = (
            "import socket, subprocess, sys, time\n"
            "for _ in range(100):\n"
            "    with socket.socket() as s:\n"
            f"        if s.connect_ex(({host!r}, {port})) != 0: break\n"
            "    time.sleep(0.2)\n"
            # --no-browser: the open tab reloads itself once the new version answers.
            "subprocess.Popen([sys.executable, '-m', 'fleetdesk', '--no-browser'])\n"
        )
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        subprocess.Popen(
            [str(self.runtime / "pythonw.exe"), "-c", waiter],
            cwd=str(self.runtime.parent),
            creationflags=flags,
            close_fds=True,
        )
