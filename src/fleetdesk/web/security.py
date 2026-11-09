"""Keep the local server reachable only by its own pages.

The server listens on 127.0.0.1, but any website open in the same browser could still send
requests to it. Checking ``Host`` defeats DNS-rebinding, and checking ``Origin`` on writes
stops other sites from changing settings or popping file dialogs.
"""

from __future__ import annotations

from flask import Flask, abort, request


def install_local_only_guard(app: Flask) -> None:
    @app.before_request
    def _guard() -> None:
        allowed_hosts: set[str] = app.config["ALLOWED_HOSTS"]
        if request.host not in allowed_hosts:
            abort(403)
        origin = request.headers.get("Origin")
        if (
            request.method == "POST"
            and origin
            and origin.removeprefix("http://") not in allowed_hosts
        ):
            abort(403)
