from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from flask.testing import FlaskClient

from fleetdesk.settings import SettingsStore
from fleetdesk.updates import UpdateChecker, UpdateError, is_newer, parse_version
from tests.conftest import FakeReleases, ShutdownSpy

PYTHON_DLL = "python314.dll"


def make_runtime(root: Path, version: str) -> Path:
    """A minimal stand-in for the bundled runtime folder of an installed FleetDesk."""
    runtime = root / "FleetDesk" / "runtime"
    package = runtime / "Lib" / "site-packages" / "fleetdesk"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(f'__version__ = "{version}"\n')
    (runtime / PYTHON_DLL).write_bytes(b"dll")
    (runtime / "python314._pth").write_text("python314.zip\n")
    return runtime


def make_bundle(version: str, python_dll: str = PYTHON_DLL) -> bytes:
    """A release zip laid out like scripts/build_portable.py produces."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        prefix = "FleetDesk/runtime/"
        bundle.writestr(f"{prefix}{python_dll}", b"dll")
        bundle.writestr(
            f"{prefix}Lib/site-packages/fleetdesk/__init__.py", f'__version__ = "{version}"\n'
        )
        bundle.writestr(f"{prefix}Lib/site-packages/flask/__init__.py", "")
        bundle.writestr("FleetDesk/LEIA-ME.txt", "leia")
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("candidate", "current", "newer"),
    [("0.2.0", "0.1.0", True), ("v0.10.0", "0.9.9", True), ("0.1.0", "0.1.0", False),
     ("0.1.0", "0.2.0", False), ("garbage", "0.1.0", False)],
)  # fmt: skip
def test_version_comparison(candidate: str, current: str, newer: bool) -> None:
    assert is_newer(candidate, current) is newer
    assert parse_version("v1.2.3-rc1") == (1, 2, 3)


def test_offline_check_shows_nothing(releases: FakeReleases) -> None:
    checker = UpdateChecker("0.1.0", fetch=releases, runtime=None)
    assert checker.available(force=True) is None


def test_newer_release_is_reported_and_cached(releases: FakeReleases) -> None:
    releases.publish("0.2.0", make_bundle("0.2.0"))
    checker = UpdateChecker("0.1.0", fetch=releases, runtime=None)

    assert checker.cached() is None  # nothing until the first check
    release = checker.available(force=True)
    assert release is not None and release.version == "0.2.0"
    releases.offline = True
    assert checker.cached() == release  # pages read the cache, never the network


def test_update_swaps_only_the_python_packages(tmp_path: Path, releases: FakeReleases) -> None:
    runtime = make_runtime(tmp_path, "0.1.0")
    releases.publish("0.2.0", make_bundle("0.2.0"))
    checker = UpdateChecker("0.1.0", fetch=releases, runtime=runtime)
    release = checker.available(force=True)
    assert release is not None

    staged = checker.prepare(release)
    checker.activate(staged)

    site = runtime / "Lib" / "site-packages"
    assert '"0.2.0"' in (site / "fleetdesk" / "__init__.py").read_text()
    assert (site / "flask" / "__init__.py").exists()
    assert (runtime / PYTHON_DLL).read_bytes() == b"dll"  # runtime binaries untouched
    assert not (runtime / "LEIA-ME.txt").exists()

    checker.cleanup()
    assert not (runtime / "Lib" / "site-packages.old").exists()


def test_corrupted_download_is_refused(tmp_path: Path, releases: FakeReleases) -> None:
    runtime = make_runtime(tmp_path, "0.1.0")
    releases.publish("0.2.0", make_bundle("0.2.0"))
    url = next(u for u in releases.responses if u.endswith(".zip"))
    releases.responses[url] = releases.responses[url][:-10]  # truncated download
    checker = UpdateChecker("0.1.0", fetch=releases, runtime=runtime)
    release = checker.available(force=True)
    assert release is not None

    with pytest.raises(UpdateError, match="SHA-256"):
        checker.prepare(release)
    assert '"0.1.0"' in (runtime / "Lib/site-packages/fleetdesk/__init__.py").read_text()


def test_new_python_runtime_requires_a_reinstall(tmp_path: Path, releases: FakeReleases) -> None:
    runtime = make_runtime(tmp_path, "0.1.0")
    releases.publish("0.2.0", make_bundle("0.2.0", python_dll="python315.dll"))
    checker = UpdateChecker("0.1.0", fetch=releases, runtime=runtime)
    release = checker.available(force=True)
    assert release is not None

    with pytest.raises(UpdateError, match="instalada de novo"):
        checker.prepare(release)


def test_dev_checkout_cannot_self_update(releases: FakeReleases) -> None:
    checker = UpdateChecker("0.1.0", fetch=releases, runtime=None)
    assert not checker.can_self_update


def test_banner_appears_when_an_update_is_known(
    configured_client: FlaskClient, updates: UpdateChecker, releases: FakeReleases
) -> None:
    assert "update-banner" not in configured_client.get("/dashboard").get_data(as_text=True)

    releases.publish("0.2.0", make_bundle("0.2.0"))
    updates.available(force=True)
    html = configured_client.get("/dashboard").get_data(as_text=True)

    assert "Nova versão 0.2.0 disponível" in html
    assert "Baixar" in html  # a dev checkout offers the download page instead


def test_banner_respects_the_setting(
    configured_client: FlaskClient,
    updates: UpdateChecker,
    releases: FakeReleases,
    settings_store: SettingsStore,
) -> None:
    releases.publish("0.2.0", make_bundle("0.2.0"))
    updates.available(force=True)
    configured_client.post("/settings", data={"check_updates": "0"})

    assert settings_store.load().check_updates is False
    assert "update-banner" not in configured_client.get("/dashboard").get_data(as_text=True)


def test_update_endpoint_applies_and_restarts(
    configured_client: FlaskClient,
    updates: UpdateChecker,
    releases: FakeReleases,
    shutdown_calls: ShutdownSpy,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updates.runtime = make_runtime(tmp_path / "install", "0.1.0")
    monkeypatch.setattr(updates, "relaunch_when_stopped", lambda host, port: None)
    releases.publish("0.2.0", make_bundle("0.2.0"))

    response = configured_client.post("/update")

    assert response.get_json() == {"version": "0.2.0"}
    import time

    for _ in range(50):  # the swap runs just after the response
        if shutdown_calls.calls:
            break
        time.sleep(0.05)
    assert shutdown_calls.calls == 1
    site = updates.runtime / "Lib" / "site-packages"
    assert '"0.2.0"' in (site / "fleetdesk" / "__init__.py").read_text()


def test_update_endpoint_without_an_update(configured_client: FlaskClient) -> None:
    response = configured_client.post("/update")
    assert response.status_code == 409


def test_version_endpoint(client: FlaskClient) -> None:
    from fleetdesk import __version__

    assert client.get("/version").get_json() == {"version": __version__}
