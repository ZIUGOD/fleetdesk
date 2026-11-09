from __future__ import annotations

import socket

from fleetdesk.app import is_port_in_use


def test_port_in_use_is_detected() -> None:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        port = server.getsockname()[1]
        assert is_port_in_use("127.0.0.1", port)
    assert not is_port_in_use("127.0.0.1", port)
