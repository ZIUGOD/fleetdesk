"""Application factory and command-line entry point."""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import threading
import webbrowser
from logging.handlers import RotatingFileHandler
from typing import Any

from flask import Flask, Response, g, request, url_for

from fleetdesk import __version__, formatting
from fleetdesk.assistant import LocalAssistant
from fleetdesk.data.repository import DataRepository
from fleetdesk.dialogs import pick_path
from fleetdesk.settings import SettingsStore, default_settings_path
from fleetdesk.updates import DOWNLOAD_PAGE, UpdateChecker
from fleetdesk.web.routes import audit_for, bp, load_dataset
from fleetdesk.web.security import install_local_only_guard
from fleetdesk.web.services import Services, services

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5000

log = logging.getLogger("fleetdesk")


def create_app(
    services_override: Services | None = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> Flask:
    app = Flask(__name__)
    app.config["ALLOWED_HOSTS"] = {f"{host}:{port}", f"localhost:{port}"}
    app.config["SERVER_ADDRESS"] = (host, port)

    app_services = services_override or Services(
        settings=SettingsStore(default_settings_path()),
        repository=DataRepository(),
        pick_path=pick_path,
        shutdown=_exit_soon,
        assistant=LocalAssistant(),
        updates=UpdateChecker(),
    )
    app_services.install(app)

    formatting.register(app)
    install_local_only_guard(app)
    app.register_blueprint(bp)
    app.context_processor(_layout_context)
    app.add_template_global(url_with)
    app.after_request(_never_cache_pages)
    return app


def _exit_soon() -> None:
    # Delay so the "FleetDesk foi encerrado" page reaches the browser before the exit.
    threading.Timer(0.5, os._exit, args=(0,)).start()


def _configure_logging() -> None:
    handlers: list[logging.Handler] = []
    if sys.stderr is None:
        # Started with pythonw (no console window): keep a log the user can send us.
        log_file = default_settings_path().parent / "fleetdesk.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        )
    else:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    logging.captureWarnings(True)


def _never_cache_pages(response: Response) -> Response:
    # Pages reflect the current data source; without this, the browser's Back button
    # restores a stale copy after the user switches workbooks or folders.
    if response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-store"
    return response


def _layout_context() -> dict[str, Any]:
    settings = services().settings.load()
    dataset = g.get("dataset")
    source = settings.source
    return {
        "app_version": __version__,
        "theme": settings.theme,
        "company_name": settings.company_name,
        "source_name": os.path.basename(source.rstrip("\\/")) or source,
        "source_is_folder": os.path.isdir(source) if source else False,
        "dataset": dataset,
        "audit_alerts": audit_for(dataset).attention_count if dataset else 0,
        "update": services().updates.cached() if settings.check_updates else None,
        "can_self_update": services().updates.can_self_update,
        "download_page": DOWNLOAD_PAGE,
    }


def url_with(**params: Any) -> str:
    """URL of the current page keeping its query string, with ``params`` overridden."""
    args: dict[str, Any] = {**request.args.to_dict(), **params}
    endpoint = request.endpoint or "pages.dashboard"
    return url_for(endpoint, **{k: v for k, v in args.items() if v not in ("", None)})


def _warm_up(app: Flask) -> None:
    """Load the data and look for updates in the background, so the first page is fast."""
    with app.app_context():
        load_dataset()
        app_services = services()
        app_services.updates.cleanup()
        if app_services.settings.load().check_updates:
            release = app_services.updates.available()
            if release:
                log.info("Update available: %s", release.version)


def is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((host, port)) == 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="fleetdesk", description="FleetDesk local dashboard")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    args = parser.parse_args()

    _configure_logging()
    url = f"http://{DEFAULT_HOST}:{args.port}"
    if is_port_in_use(DEFAULT_HOST, args.port):
        # Windows lets a second server bind the same port silently, and the old one keeps
        # answering. Reuse the running instance instead (e.g. a double-clicked launcher).
        log.info("FleetDesk is already running at %s; opening it", url)
        if not args.no_browser:
            webbrowser.open(url)
        return

    app = create_app(port=args.port)
    threading.Thread(target=_warm_up, args=(app,), daemon=True).start()
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()

    from waitress import serve

    log.info("FleetDesk %s running at %s", __version__, url)
    serve(app, host=DEFAULT_HOST, port=args.port, threads=8)
